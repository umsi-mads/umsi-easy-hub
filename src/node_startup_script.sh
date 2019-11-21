#!/bin/bash

# Log to file (in admin home directory)
set -x
exec > >(tee ~/user-data.log|logger -t user-data ) 2>&1

cd /home/ec2-user/

EFSID="EFSIDREPLACE"

# Sanity check
echo $EFSID > /home/ec2-user/efsid.txt

# Sanity check of args
cd /home/ec2-user/
for X in "$@"
do
echo $X >> args.txt
done

BASE_TARGET_GROUP=$1

# Install pythonn3
sudo amazon-linux-extras install python3 -y
sudo pip3 install boto3

mkdir mnt

# Used for easily configuring EFS
yum install -y amazon-efs-utils

# Configure AWS region and then sanity check
mkdir ~/.aws/ && echo -e '[default]\nregion = us-east-1\n' > ~/.aws/config
export INFO="$(aws efs describe-mount-targets --file-system-id $EFSID)"
echo $INFO > info.txt

# Mount all possible EFS endpoints (quick and dirty way of mounting proper endpoint). There's on in each subnet
# this is probably deprecated now that the cluster is only in one subnet
OUTPUT=$(python << END
import sys, os, json
mountTargets = json.loads(os.environ['INFO'])['MountTargets']
ipArray = []
for mt in mountTargets:
    ipArray.append(mt['IpAddress'])
ipStr = ' '.join(ipArray)
print ipStr
END)

echo $OUTPUT > output.txt
IFS=" " read -a IPARR <<< "$OUTPUT"
for IP in "${IPARR[@]}"; do
    timeout 5 mount -t nfs -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport $IP:/ mnt 
done

chmod -R 777 mnt/shared

# Register with aws application load balancer
ARN_HTTP=$(python3 get_target_group.py "${BASE_TARGET_GROUP}-http")
echo $ARN_HTTP
aws elbv2 register-targets --target-group-arn $ARN_HTTP --targets Id=$(curl http://169.254.169.254/latest/meta-data/instance-id),Port=30254 --region us-east-1
ARN_HTTPS=$(python3 get_target_group.py "${BASE_TARGET_GROUP}-https")
echo $ARN_HTTPS
aws elbv2 register-targets --target-group-arn $ARN_HTTPS --targets Id=$(curl http://169.254.169.254/latest/meta-data/instance-id),Port=30255 --region us-east-1