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

CLUSTER_NAME=$1
NODE_IAM_ROLE=$2
JUPYTERHUB_IMAGE=$3
STACK_NAME=$4

cd /home/ec2-user/
export HOME=/home/ec2-user/
export PATH=/usr/local/bin/:$PATH && echo "export PATH=/usr/local/bin/:$PATH" >> ~/.bashrc

# Get kubectl binary which will expose control plane configuration options
curl -o kubectl https://amazon-eks.s3-us-west-2.amazonaws.com/1.11.5/2018-12-06/bin/linux/amd64/kubectl
chmod +x ./kubectl
sudo cp ./kubectl /usr/local/bin/kubectl

# Get aws-iam-authenticator to authenticate kubectl binary with our EKS backplane
curl -o aws-iam-authenticator https://amazon-eks.s3-us-west-2.amazonaws.com/1.11.5/2018-12-06/bin/linux/amd64/aws-iam-authenticator
chmod +x ./aws-iam-authenticator
sudo cp ./aws-iam-authenticator /usr/local/bin/aws-iam-authenticator

# Install aws cli
echo yes | sudo amazon-linux-extras install python3
sudo rm /usr/bin/aws
pip3 install --upgrade awscli --user
sudo cp ~/.local/bin/aws /usr/bin/aws

# Configure aws cli
mkdir /home/ec2-user/.aws
echo -e "[default]\nregion = us-east-1" > /home/ec2-user/.aws/config
chown -R 1000:100 /home/ec2-user/.aws/

# Sync kubectl with the EKS we want
aws eks update-kubeconfig --name $CLUSTER_NAME
curl -O https://amazon-eks.s3-us-west-2.amazonaws.com/cloudformation/2019-01-09/aws-auth-cm.yaml
sed -i -e "s/<ARN of instance role (not instance profile)>/$NODE_IAM_ROLE/g" aws-auth-cm.yaml
kubectl apply -f aws-auth-cm.yaml

# Install tiller role to apply helm charts
curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get | bash
kubectl --namespace kube-system create serviceaccount tiller
kubectl create clusterrolebinding tiller --clusterrole cluster-admin --serviceaccount=kube-system:tiller
helm init --service-account tiller
sleep 5m

# Apply helm chart to cluster
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update
export RELEASE=jhub
export NAMESPACE=jhub
helm upgrade --install $RELEASE $JUPYTERHUB_IMAGE --namespace $NAMESPACE --version 0.8.2 --values config.yaml