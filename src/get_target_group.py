import boto3
import sys

target_group_name = sys.argv[1]

client = boto3.client('elbv2', region_name='us-east-1')
response = client.describe_target_groups()

for group in response['TargetGroups']:
    if group['TargetGroupName'] == target_group_name:
        print(group['TargetGroupArn'])
