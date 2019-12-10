#!/bin/bash

# Log to file
set -x
exec > >(tee ~/user-data.log|logger -t user-data ) 2>&1

# Sanity check of args
cd /home/ec2-user/
for X in "$@"
do
echo $X >> args.txt
done

# Gather args passed to script
STACK_NAME=$1
TAG=$2
SCRIPT_BUCKET=$3
JUPYTERHUB_IMAGE="jupyterhub/jupyterhub"

# Ensure you are in the home directory of ec2-user
cd /home/ec2-user/
export HOME=/home/ec2-user/

# Include the local binaries in the path (this is where we will put the aws and kubectl binaries)
export PATH=/usr/local/bin/:$PATH && echo "export PATH=/usr/local/bin/:$PATH" >> ~/.bashrc

# Download files from s3
aws s3 cp s3://${SCRIPT_BUCKET}/config.yaml .
aws s3 cp s3://${SCRIPT_BUCKET}/control_node_startup_script.sh .
aws s3 cp s3://${SCRIPT_BUCKET}/cluster_cf.yaml .
aws s3 cp s3://${SCRIPT_BUCKET}/deploy_cluster_cf.py .
aws s3 cp s3://${SCRIPT_BUCKET}/autoscale_daemon.py .
aws s3 cp s3://${SCRIPT_BUCKET}/umsi-easy-hub-${TAG}.pem .
aws s3 cp s3://${SCRIPT_BUCKET}/generate_hex.py .
aws s3 cp s3://${SCRIPT_BUCKET}/set_pod_memory.py .
aws s3 cp s3://${SCRIPT_BUCKET}/get_cluster_cf_output.py .
aws s3 cp s3://${SCRIPT_BUCKET}/helm_config.yaml .

# Install packages
sudo yum install python37 python37-pip -y
sudo pip3 install boto3
sudo pip3 install pyyaml

# Configure aws cli region
mkdir /home/ec2-user/.aws
echo -e "[default]\nregion = us-east-1" > /home/ec2-user/.aws/config
sudo chown -R 1000:100 /home/ec2-user/.aws/

# Deploy cluster cloudformation stack. This includes the EKS, EFS, Autoscaler, and Loadbalancer
# This script needs output from the control node cloudformation stack
python3 deploy_cluster_cf.py --control-node-stackname ${STACK_NAME}

# Wait for the cluster cloudformation stack to complete before continuing...
aws cloudformation wait stack-create-complete --stack-name "umsi-easy-hub-${TAG}-cluster"

# Get output of cloudformation stack
output=($(python3 get_cluster_cf_output.py --cluster-stackname "umsi-easy-hub-${TAG}-cluster") )
# ${output[0]} = Tag
# ${output[1]} = EksName
# ${output[2]} = NodeRoleArn
# ${output[3]} = Asg

# Get kubectl binary which will expose control plane configuration options
curl -o kubectl https://amazon-eks.s3-us-west-2.amazonaws.com/1.11.5/2018-12-06/bin/linux/amd64/kubectl
chmod +x ./kubectl
sudo cp ./kubectl /usr/local/bin/kubectl

# Get aws-iam-authenticator to authenticate kubectl binary with our EKS backplane
curl -o aws-iam-authenticator https://amazon-eks.s3-us-west-2.amazonaws.com/1.11.5/2018-12-06/bin/linux/amd64/aws-iam-authenticator
chmod +x ./aws-iam-authenticator
sudo cp ./aws-iam-authenticator /usr/local/bin/aws-iam-authenticator

# Install aws cli
# echo yes | sudo amazon-linux-extras install python3
sudo rm /usr/bin/aws
pip3 install --upgrade awscli --user
sudo cp ~/.local/bin/aws /usr/bin/aws

# Sync kubectl with the EKS we want
aws eks update-kubeconfig --name ${output[1]}
curl -O https://amazon-eks.s3-us-west-2.amazonaws.com/cloudformation/2019-01-09/aws-auth-cm.yaml
sed -i -e "s;<ARN of instance role (not instance profile)>;${output[2]};g" aws-auth-cm.yaml
kubectl apply -f aws-auth-cm.yaml

# Install tiller role to apply helm charts
curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get | bash
kubectl --namespace kube-system create serviceaccount tiller
kubectl create clusterrolebinding tiller --clusterrole cluster-admin --serviceaccount=kube-system:tiller
helm init --service-account tiller

# Sleep because sometimes it takes a while for the tiller pod to initialize
sleep 2m

# Generate hex key for helm config
python3 generate_hex.py

# Set user pod limit in helm config
python3 set_pod_memory.py

# Deploy helm chart to cluster
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update
export RELEASE=jhub
export NAMESPACE=jhub
helm upgrade --install $RELEASE $JUPYTERHUB_IMAGE --namespace $NAMESPACE --version 0.8.2 --values helm_config.yaml

# Add in autoscaler
sudo touch /etc/cron.d/autoscale_daemon
sudo chmod 777 /etc/cron.d/autoscale_daemon
sudo echo "* * * * * ec2-user python3 /home/ec2-user/autoscale_daemon.py --asg=${output[3]}" >> /etc/cron.d/autoscale_daemon
sudo echo "* * * * * ec2-user sleep 15 && python3 /home/ec2-user/autoscale_daemon.py --asg=${output[3]}" >> /etc/cron.d/autoscale_daemon
sudo echo "* * * * * ec2-user sleep 30 && python3 /home/ec2-user/autoscale_daemon.py --asg=${output[3]}" >> /etc/cron.d/autoscale_daemon
sudo echo "* * * * * ec2-user sleep 45 && python3 /home/ec2-user/autoscale_daemon.py --asg=${output[3]}" >> /etc/cron.d/autoscale_daemon
sudo chmod 644 /etc/cron.d/autoscale_daemon