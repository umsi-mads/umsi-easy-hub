# autoscale_daemon.py

"""
This script is to be run by the control-node's crontab at a rate specified in the cloudformation. It's purpose is to alert the autoscaling group to scale up or remove and terminate unused nodes from the autoscaling group.
It ensure's that there is always "x" open user pods latency of ~3 min.


TODO:
- make auto pep 8
- move subprocess call to it's own function and move to boto3 for aws calls
- look into fixing PATH update for aws and kubectl bin
- update overall autoscale daemon logic to run this script 24/7 (main loop w/ memory) with a crontab that monitors it
"""

# Python Libraries
import subprocess
import re
import json
import sys, os
import logging
from logging.handlers import RotatingFileHandler
import argparse
import math

# Set up logger with rotating log file
log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
logFile = '/home/ec2-user/autoscale_daemon.log'
my_handler = RotatingFileHandler(logFile, mode='a', maxBytes=5*1024*1024, backupCount=2, encoding=None, delay=0)
my_handler.setFormatter(log_formatter)
my_handler.setLevel(logging.INFO)
log = logging.getLogger('root')
log.setLevel(logging.INFO)
log.addHandler(my_handler)

# Set up arg parser
parser = argparse.ArgumentParser()
parser.add_argument("--asg", "-a", help="name of autoscaling group to manage")
parser.add_argument("--nodeMem", "-n", help="Gb of memory available on node (int)")
parser.add_argument("--userMem", "-u", help="Gb of memory to assign to each user (int)")
parser.add_argument("--availPods", '-p', help="desired open pods on standby (int)")

def parse_nodes_info(node_info):
    """Parse basic node info retreived from kubernetes controller.

    Keyword arguments:
    node_info -- list of nodes and basic info when executed 'kubectl get nodes'
    """
    nodes = {}
    for line in node_info.split('\n')[1:-1]:
        nodes[line.split()[0]] = {
            "age": convert_to_sec(line.split()[3]),
            "ready": line.split()[1] == "Ready"
        }
    return nodes

def convert_to_sec(age):
    """Converts age to seconds.

    Keyword arguments:
    age -- age of node in the format of '4d', '6h', '23m', etc.
    """
    num = int(age[0:-1])
    unit = age[-1]
    if unit == "s":
        return num
    elif unit == "m":
        return num * 60
    elif unit == "h":
        return num * 60 * 60
    elif unit == "d":
        return num * 60 * 60 * 24
    else:
        log.warning("unrecognized unit %s" % unit)
        return 3600

def get_available_pods(node_data):
    """Parses a single node's data for the current number of unused pods it has available before it becomes full.

    Keyword arguments:
    node_data -- large block of data when executed 'kubectl describe node <node-name>'
    """
    for index, line in enumerate(node_data):
        line = " ".join(line.split())
        if line.split(' ')[0] == "memory":
            log.info("Total memory reserved on node: %s" % line)
            mem_percent_available = 100 - int(re.sub('[^0-9]', '', line.split(' ')[2]))
            num_available_pods = int(mem_percent_available / user_mem_percentage)
            return num_available_pods

def node_is_empty(node_data):
    """Checks if node is empty and has no user notebook pods open on it.

    Keyword arguments:
    node_data -- large block of data when executed 'kubectl describe node <node-name>'
    """
    for index, line in enumerate(node_data):
        if len(line.split()) > 2 and "jupyter-" in line.split()[1]:
            log.info("Node has available pods but is not empty (ex. %s)" % " ".join(line.split()))
            return False

    return True

def terminable_empty_node(empty_nodes):
    """Checks if any of the nodes are terminable based on their current age. This is to avoid terminating a node too quickly.

    Keyword arguments:
    empty_nodes -- dictionary of all empty cluster nodes
    """
    if len(empty_nodes) == 0:
        return False
    
    for node in empty_nodes:
        if empty_nodes[node]['age'] >= (60 * 60):
            log.info("Terminable node: %s " % str(empty_nodes[node]))
            return node
    
    log.info("No terminable nodes")
    return False

def terminate_node(node_name, asg):
    """Terminates a nodes and removes it from the node autoscaling group.

    Keyword arguments:
    node_name -- name of node in the format ip-172-16-95-120.ec2.internal
    asg -- name of node autoscaling group
    """
    CMD = ['aws', 'ec2', 'describe-instances', '--filter', 'Name=private-ip-address,Values=%s' % ".".join(node_name.split('.')[0].split('-')[1:])]
    instance_id = json.loads(subprocess.run(CMD,stdout=subprocess.PIPE).stdout.decode('utf-8'))['Reservations'][0]['Instances'][0]['InstanceId']
    log.info("Terminating node with instace id: %s" % instance_id)
    subprocess.run(['aws', 'autoscaling', 'detach-instances', '--instance-ids', instance_id, '--auto-scaling-group-name', asg, '--should-decrement-desired-capacity'])
    subprocess.run(['aws', 'ec2', 'terminate-instances', '--instance-ids', instance_id])

if __name__=="__main__":
    
    # Add necessary executables (such as aws binary) to path of root user that calls this file in crontab
    my_env = os.environ
    my_env["PATH"] = "/usr/local/bin:" + my_env["PATH"]

    # Log initialization to file
    log.info("Initializing autoscaling...")

    # Get args
    args = parser.parse_args()

    log.info("%s %s %s %s" % (args.asg, args.nodeMem, args.userMem, args.availPods))

    # A node with max number of users is a "full node"
    # max_users is calculated based on 1Gb of overhead services like proxy and hub
    user_mem_percentage = math.ceil(float(args.userMem) / float(args.nodeMem) * 100)
    log.info("user_mem_percentage is %s" % user_mem_percentage)

    empty_nodes={}
    full_nodes={}
    available_nodes={}
    total_available_pods=0

    # Get kubernetes node ips and basic info
    nodes_info = subprocess.run(["kubectl", "get", "nodes"],stdout=subprocess.PIPE).stdout.decode('utf-8')
    log.info("Node Info:\n%s" % nodes_info)
    nodes = parse_nodes_info(nodes_info)
    

    # Get node data for each node and sort into available, empty, and full. Also calculate number of available pods along the way
    for node in nodes:
        log.info("Checking node %s" % node)
        node_data = subprocess.run(['kubectl', 'describe', 'node/%s' % node ],stdout=subprocess.PIPE).stdout.decode('utf-8').split('\n')
        num_available_pods = get_available_pods(node_data)
        if num_available_pods == 0:
            full_nodes[node] = nodes[node]
        else:
            available_nodes[node] = nodes[node]
            total_available_pods += num_available_pods
            if node_is_empty(node_data):
                empty_nodes[node] = nodes[node]
    
    # Log results of sorting
    log.info("total available pods: " + str(total_available_pods))
    log.info("empty nodes (%s): %s" % (str(len(empty_nodes)), str(empty_nodes)))
    log.info("full nodes (%s): %s" % (str(len(full_nodes)), str(full_nodes)))
    log.info("available nodes (%s): %s" % (str(len(available_nodes)), str(available_nodes)))

    # Decide whether to scale up, scale down, or silent the scale up alarm
    if total_available_pods < int(args.availPods):
        log.info("Not enough available pods. Sending alarm to scale up cluster...")
        subprocess.run(["aws", "cloudwatch", "put-metric-data", "--metric-name", "available-space", "--dimensions", "cluster=%s" % args.asg,  "--namespace", "Custom", "--value", "0"],stdout=subprocess.PIPE).stdout.decode('utf-8')
        log.info("Scale up alarm sent.")
    elif (total_available_pods - int((100/user_mem_percentage))) >= int(args.availPods) and terminable_empty_node(empty_nodes):
        log.info("Scaling cluster down...")
        node_to_terminate = terminable_empty_node(empty_nodes)
        terminate_node(node_to_terminate, args.asg)
        log.info("Scaled down cluster.")
    else:
        log.info("Silent the scale up alarm.")
        subprocess.run(["aws", "cloudwatch", "put-metric-data", "--metric-name", "available-space", "--dimensions", "cluster=%s" % args.asg,  "--namespace", "Custom", "--value", "1"])

    # Check for failing nodes
    for node in nodes:
        if nodes[node]['ready'] == False and nodes[node]['age'] > (8 * 60):
            log.warning("Node %s is unstable. Terminating..." % node)
            terminate_node(node, args.asg)
            log.info("Node terminated.")

    log.info("Autoscaling finished.")