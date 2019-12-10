# This is a quick helper script to get the output values from the cluster cloudformation
# It is executed on the control node after the entire cluster cloudformationn is deployed

import boto3
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--cluster-stackname", "-s", required=True, help="stackname of previous cloudformation")

args = parser.parse_args()

stackname = args.cluster_stackname

# Still need to add logging!!!

cf_client = boto3.client('cloudformation', region_name='us-east-1')

response = cf_client.describe_stacks(
    StackName=stackname
)

# print(response)

output = {}
for item in response['Stacks'][0]['Outputs']:
    output[item['OutputKey']] = item['OutputValue']

# print(output)

print(output['Tag'], output['EksName'], output['NodeRoleArn'], output['Asg'])