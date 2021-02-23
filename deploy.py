# This script deploys the control node cloudformation, which will then automatically deploy and configure the cluster
# cloudformation and kubernetes deployment.

import os, stat, sys
import boto3
import re
import argparse
import json
from shutil import copyfile
import yaml

# This should never have to change. This is used in tagging/identifying all aws resources
project = "umsi-easy-hub"

secrets = boto3.client('secretsmanager')

# Loads from config.yaml. Currently, nothing from this file is actually needed at this point.
def load_config(tag="dev"):
    config = {}
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
        config = {**config['common']}
        print(config)
        for c in config:
            if config[c] is None or config[c] == "":
                raise Exception("Error. {} does not have a valid value")

    return config

# Generate a new ssh key that will be used for all nodes throughout the deployment
def generate_ssh_key(config):
    """Generate an SSH key pair from EC2 and save it to Secrets Manager."""
    ec2 = boto3.client('ec2')
    response = ec2.create_key_pair(KeyName='{}-{}'.format(config['project'], config['tag']))

    name = "{}.pem".format(response['KeyName'])

    with open(name, 'w') as f:
        f.write(response['KeyMaterial'])

    # Only owner can only read
    os.chmod(name, stat.S_IREAD)

    return response['KeyName']

# Create the S3 bucket that will centrally store scripts used throughout the deployment process
def create_bucket(config):
    """Create an S3 bucket for use by this cluster's control node."""
    print(config['account_id'])

    bucket_name = get_bucket_name(config)
    s3_client = boto3.client('s3')
    response = s3_client.create_bucket(ACL='private', Bucket=bucket_name)

    print("Created S3 bucket {}".format(bucket_name))

    return bucket_name

# Helper script to generate S3 bucket name
def get_bucket_name(config):
    return "{}-{}-{}".format(config['account_id'], config['project'], config['tag'])

# Upload all scripts in the src/ folder to the S3 bucket
def upload_cluster_scripts(config):
    s3_resource = boto3.resource('s3')

    for filename in os.listdir('src'):
        print(filename)
        s3_resource.meta.client.upload_file('src/' + filename, get_bucket_name(config), filename)

# Deploy the control node cloudformation
def create_control_node(config):

    cf = boto3.client('cloudformation')

    with open('src/control_node_cf.yaml') as template_fileobj:
        template_data = template_fileobj.read()
    cf.validate_template(TemplateBody=template_data)

    response = cf.create_stack(
        StackName='{}-{}-control-node'.format(config['project'], config['tag']),
        TemplateBody=template_data,
        Parameters=[
            {
                'ParameterKey': 'BillingTag', 'ParameterValue': '{}-{}'.format(config['project'], config['tag']), 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'ScriptBucket', 'ParameterValue': get_bucket_name(config), 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'KeyName', 'ParameterValue': config['ssh_key_name'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'Tag', 'ParameterValue': config['tag'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'PrivateKey', 'ParameterValue': open(config['ssh_key_name']+'.pem', 'r').read(), 'UsePreviousValue': False
            }
        ],
        Capabilities=[
            'CAPABILITY_NAMED_IAM'
        ],
    )
    print("deployed stack!")

def fail(msg):
    print(msg)
    sys.exit(1)

if __name__ == "__main__":

    # The only argument required is the tag that makes this deployment and all its resources unique.
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", "-t",
                        required=False,
                        default = "test",
                        help="tag to build, must be alphanumeric like \"prod\" or \"test\"")

    parser.add_argument("--project", "-p",
                        required=False,
                        default = "umsi-easy-hub",
                        help="name of project, used in all AWS resources")

    parser.add_argument("--wait", "-w",
                        required=False,
                        default=False,
                        action='store_true',
                        help="wait until the control node has completed and display it's public IP address")

    args = parser.parse_args()

    if args.project != "umsi-easy-hub":
        fail("Using a different project name is currently unsupported.")

    if len(args.tag) > 9:
        fail("Due to limitations in AWS, the tag name must be a max length of 9.")

    # Generate basic config
    config = {}
    config['tag'] = args.tag
    config['project'] = args.project
    config['account_id'] = boto3.client('sts').get_caller_identity().get('Account')
    config['ssh_key_name'] = generate_ssh_key(config)
    print(config)

    # Create an S3 bucket
    create_bucket(config)

    # Upload all files in src/ to the bucket
    upload_cluster_scripts(config)

    # Finally, deploy the control node cloudformation
    create_control_node(config)

    if args.wait:
        print("Waiting for your cloudformation to finish contructing")
        boto3.client('cloudformation').get_waiter('stack_create_complete').wait(StackName='umsi-easy-hub-shreve-control-node')
        outputs = boto3.resource('cloudformation').Stack('umsi-easy-hub-shreve-control-node').outputs

        instance = next((x for x in outputs if x['OutputKey'] == 'Instance'), None)

        if instance:
            print("Connect to your control node: ssh -i {} ec2-user@{}".format(
                config['ssh_key_name'],
                boto3.resource('ec2').Instance(instance['OutputValue']).public_ip_address
            ))

