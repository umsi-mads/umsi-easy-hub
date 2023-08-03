#!/bin/bash

# Log to file
set -x
exec > >(tee ~/user-data.log|logger -t user-data ) 2>&1

# Quit on error
set -e

# Sanity check of args
for X in "$@"; do
    echo "$X" >> args.txt
done

# Gather args passed to script
export STACK_NAME=$1
export TAG=$2
export SCRIPT_BUCKET=$3

# Ensure you are in the home directory of ec2-user
cd /home/ec2-user/ || exit
export HOME=/home/ec2-user/

# Include the local binaries in the path (this is where we will put the aws and kubectl binaries)
export PATH=/usr/local/bin/:$PATH && echo "export PATH=/usr/local/bin/:$PATH" >> ~/.bashrc

# Install aws cli v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Install kubectl binary which will expose control plane configuration options
curl -o kubectl https://amazon-eks.s3.us-west-2.amazonaws.com/1.21.2/2021-07-05/bin/linux/amd64/kubectl
chmod +x ./kubectl
sudo cp ./kubectl /usr/local/bin/kubectl

# Install eksctl for AWS-specific operations inside an EKS cluster
curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin

# Download files from s3
aws s3 cp --recursive "s3://$SCRIPT_BUCKET/" .

# Fetch the SSH key from the secret store
# export KEY_NAME="umsi-easy-hub-$TAG.pem"
# aws secretsmanager get-secret-value --secret-id $KEY_NAME \
#   --query SecretString --output text > $KEY_NAME

# Install packages
sudo yum install python37 python37-pip -y
sudo pip3 install boto3 pyyaml

# Configure aws cli region
mkdir /home/ec2-user/.aws
echo -e "[default]\nregion = us-east-1" > /home/ec2-user/.aws/config
sudo chown -R 1000:100 /home/ec2-user/.aws/

# Deploy cluster cloudformation stack. This includes the EKS, EFS, Autoscaler, and Loadbalancer
# This script needs output from the control node cloudformation stack
python3 deploy_cluster_cf.py --control-node-stackname "$STACK_NAME"

# Wait for the cluster cloudformation stack to complete before continuing...
aws cloudformation wait stack-create-complete --stack-name "umsi-easy-hub-$TAG-cluster"

# Get output of cloudformation stack
IFS=" " read -r -a output <<< "$(python3 get_cluster_cf_output.py --cluster-stackname "umsi-easy-hub-$TAG-cluster")"
echo "${output[*]}"
export EKS_NAME="${output[0]}"
export NODE_ROLE_ARN="${output[1]}"
export ASG_ARN="${output[2]}"
# ${output[0]} = Tag
# ${output[1]} = EksName
# ${output[2]} = NodeRoleArn
# ${output[3]} = Asg

# Get aws-iam-authenticator to authenticate kubectl binary with our EKS backplane
curl -o aws-iam-authenticator https://amazon-eks.s3-us-west-2.amazonaws.com/1.11.5/2018-12-06/bin/linux/amd64/aws-iam-authenticator
chmod +x ./aws-iam-authenticator
sudo cp ./aws-iam-authenticator /usr/local/bin/aws-iam-authenticator

# Sync kubectl with the EKS we want
aws eks update-kubeconfig --name "$EKS_NAME"
curl -O https://amazon-eks.s3-us-west-2.amazonaws.com/cloudformation/2019-01-09/aws-auth-cm.yaml
sed -i -e "s;<ARN of instance role (not instance profile)>;$NODE_ROLE_ARN;g" aws-auth-cm.yaml
kubectl apply -f aws-auth-cm.yaml

# Upgrade some internal components of the cluster
eksctl utils update-kube-proxy --cluster "$EKS_NAME" --approve
eksctl utils update-aws-node --cluster "$EKS_NAME" --approve
eksctl utils update-coredns --cluster "$EKS_NAME" --approve

aws eks create-addon \
    --cluster-name "$EKS_NAME" \
    --addon-name vpc-cni \
    --addon-version v1.9.0 \
    --service-account-role-arn "$NODE_ROLE_ARN" \
    --resolve-conflicts OVERWRITE

# Install Helm per https://helm.sh/docs/intro/install/
curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash

# Generate hex key for helm config
python3 generate_hex.py

# Set user pod limit in helm config
python3 set_pod_memory.py

# Deploy helm chart to cluster
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update
export RELEASE=jhub
export NAMESPACE=jhub
export JUPYTERHUB_IMAGE="jupyterhub/jupyterhub"

# Create namespace because helm expects it to exist already.
kubectl create namespace $NAMESPACE
helm upgrade --install $RELEASE $JUPYTERHUB_IMAGE --namespace $NAMESPACE --version 0.8.2 --values helm_config.yaml

# Add in autoscaler
sudo touch /etc/cron.d/autoscale_daemon
sudo chmod 777 /etc/cron.d/autoscale_daemon
echo "* * * * * ec2-user python3 /home/ec2-user/autoscale_daemon.py --asg=$ASG_ARN
* * * * * ec2-user sleep 15 && python3 /home/ec2-user/autoscale_daemon.py --asg=$ASG_ARN
* * * * * ec2-user sleep 30 && python3 /home/ec2-user/autoscale_daemon.py --asg=$ASG_ARN
* * * * * ec2-user sleep 45 && python3 /home/ec2-user/autoscale_daemon.py --asg=$ASG_ARN" | sudo tee -a /etc/cron.d/autoscale_daemon
sudo chmod 644 /etc/cron.d/autoscale_daemon

env
