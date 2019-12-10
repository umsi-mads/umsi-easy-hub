import boto3
import argparse
import yaml

# Still need to add logging!!!
# Currently, the print statements should be caught by the control_node_startup_script.sh logger

# This should never have to change. This is used in tagging/identifying all aws resources
project = "umsi-easy-hub"

# Boto client to control cloudformation
cf_client = boto3.client('cloudformation', region_name='us-east-1')

# Loads from config.yaml. Currently, nothing from this file is actually needed at this point.
def load_config(global_config):
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
        global_config.update(config['common'])
        print(global_config)
        for c in global_config:
            if global_config[c] is None or global_config[c] == "":
                raise Exception("Error. {} does not have a valid value")

    return global_config

# Get important output values from the control node cloudformation deployment such as VPC id's and Subnet id's
def get_cf_output(config):

    response = cf_client.describe_stacks(
        StackName=config['ControlNodeStackname']
    )

    print(response)

    output = {}
    for item in response['Stacks'][0]['Outputs']:
        output[item['OutputKey']] = item['OutputValue']
    
    config.update(output)
    # config['tag'] = 'test'

    return config

# Deploy the cluster cloudformation using the boto client
def create_cluster(config):

    # Validate the template to make sure there are no obvious errors
    with open('cluster_cf.yaml') as template_fileobj:
        template_data = template_fileobj.read()
    cf_client.validate_template(TemplateBody=template_data)

    # Create the cloudformation stack using parameters gathered from the config map
    response = cf_client.create_stack(
        StackName='{}-{}-cluster'.format(config['Project'], config['Tag']),
        TemplateBody=template_data,
        Parameters=[
            {
                'ParameterKey': 'Tag', 'ParameterValue': config['Tag'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'BillingTag', 'ParameterValue': config['BillingTag'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'ScriptBucket', 'ParameterValue': config['ScriptBucket'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'KeyName', 'ParameterValue': config['KeyName'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'VpcId', 'ParameterValue': config['VpcId'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'Subnet01Id', 'ParameterValue': config['Subnet01Id'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'Subnet02Id', 'ParameterValue': config['Subnet02Id'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'Subnet03Id', 'ParameterValue': config['Subnet03Id'], 'UsePreviousValue': False
            },
            {
                'ParameterKey': 'ControlNodeSecurityGroup', 'ParameterValue': config['ControlNodeSecurityGroup'], 'UsePreviousValue': False
            }
        ],
        Capabilities=[
            'CAPABILITY_NAMED_IAM'
        ],
    )
    print("deployed stack!")

if __name__ == "__main__":

    # This script takes in one variable, which is the name of the control node cloudformation (so that we can look up outputs from it)
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-node-stackname", "-s", required=True, help="stackname of previous cloudformation")

    args = parser.parse_args()

    stackname = args.control_node_stackname

    # Generate basic config
    config = {}
    config['ControlNodeStackname'] = stackname
    config['Project'] = project
    config['AccountId'] = boto3.client('sts').get_caller_identity().get('Account')

    config = get_cf_output(config)

    config = load_config(config)

    print(config)

    # Now deploy the cluster cloudformation
    create_cluster(config)


