#!/bin/bash

if grep '^[-0-9a-zA-Z]*$' <<<$1 && [ ! -z "$1" ];
  then echo "Tag is valid";
  else echo "Tag must be alphanumeric." && exit 1;
fi

TAG=$1
PROJECT="umsi-easy-hub"

aws ec2 delete-key-pair --key-name "$PROJECT-$TAG"
#aws iam delete-role --role-name "easy-deploy-jupyterhub-role-$(shell cat dist/stage)"
rm "$PROJECT-$TAG.pem"
rm -rf dist
# aws cloudformation delete-stack --stack-name "jupyterhub-$(shell cat dist/stage)"