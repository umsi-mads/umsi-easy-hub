import yaml
# from cfn_tools import load_yaml, dump_yaml
import os
import ruamel.yaml
import boto3
import re
import argparse
from shutil import copyfile
import subprocess

dist_path = "dist/"
template_file = "src/cloudformation_template.yaml"

def load_config(stage="dev"):
    config = {}
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
        config = {**config['common']}
        print(config)
        for c in config:
            if config[c] is None or config[c] == "":
                raise Exception("Error. {} does not have a valid value")
    
    return config

def create_bucket(config):
    account_id = boto3.client('sts').get_caller_identity().get('Account')
    print(account_id)

    bucket_name = "{}-jupyterhub-{}".format(account_id, config['stage'])

    s3_client = boto3.client('s3')

    response = s3_client.create_bucket(ACL='private', Bucket=bucket_name)

    return bucket_name

def get_bucket_name(config):
    account_id = boto3.client('sts').get_caller_identity().get('Account')
    return "{}-jupyterhub-{}".format(account_id, config['stage'])

def verify_config(config):
    print(config)

def configure_cloudformation_template(config):

    with open("src/cloudformation_template.yaml", 'r') as f:
        cf_raw = f.read()
        # print(cf_raw)
        cf_yaml = ruamel.yaml.round_trip_load(cf_raw, preserve_quotes=True)
    
    with open("src/helm_config.yaml", 'r') as f:
        helm_yaml = yaml.safe_load(f)
        print(helm_yaml)

    #print(dump_yaml(cf_yaml))

    print(config)
    #cf_yaml['Parameters']['DefaultAlbForwardPort']['Default'] = config['HttpsPort']
    cf_yaml['Parameters']['ClusterStage']['Default'] = config['stage']
    cf_yaml['Parameters']['ScriptBucket']['Default'] = get_bucket_name(config)
    cf_yaml['Parameters']['UserPodMem']['Default'] = int(helm_yaml['singleuser']['memory']['limit'][:-1])
    cf_yaml['Parameters']['KeyName']['Default'] = config['SSHKeyName']
    cf_yaml['Parameters']['ControlNodeRole']['Default'] = config['ControlNodeRole']

    with open(dist_path + "cloudformation.yaml", "w") as f:
        ruamel.yaml.round_trip_dump(cf_yaml, f, explicit_start=True)

def configure_cluster_scripts(config):

    scripts = [
        "autoscale_daemon.py",
        "control_node_startup_script.sh",
        "helm_config.yaml",
        "node_startup_script.sh",
        "get_target_group.py"
    ]

    for script in scripts:
        copyfile("src/" + script, "dist/" + script)

    with open("dist/helm_config.yaml", 'r') as f:
        helm_config = yaml.safe_load(f)
    
    helm_config['proxy']['secretToken'] = subprocess.run(['openssl', 'rand', "-hex", "32"], stdout=subprocess.PIPE, timeout=None).stdout.decode('utf-8')[:-1]
    print(helm_config)
    with open("dist/helm_config.yaml", 'w') as f:
        yaml.safe_dump(helm_config, f)

def upload_cluster_scripts(config):

    s3_resource = boto3.resource('s3')

    for filename in os.listdir('dist'):
        print(filename)

        s3_resource.meta.client.upload_file('dist/' + filename, get_bucket_name(config), filename)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", "-s", required=True, help="stage to build, either dev or prod")

    args = parser.parse_args()

    stage = args.stage

    config = load_config(stage)
    config['stage'] = stage
    print(config)
    create_bucket(config)

    if not os.path.exists(dist_path):
        os.mkdir(dist_path)

    configure_cloudformation_template(config)

    configure_cluster_scripts(config)

    upload_cluster_scripts(config)
