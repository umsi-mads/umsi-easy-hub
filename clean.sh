#!/bin/bash


# This is an unfinished script that will delete the cluster cloudformation along with any other loose ends
# Execute it with a tag to identify which cluster to delete such as "./clean.sh tag"

if grep '^[-0-9a-zA-Z]*$' <<<$1 && [ ! -z "$1" ];
  then echo "Tag is valid";
  else echo "Tag must be alphanumeric." && exit 1;
fi

TAG=$1
PROJECT="umsi-easy-hub"

aws ec2 delete-key-pair --key-name "$PROJECT-$TAG"
rm -f "$PROJECT-$TAG.pem"
rm -rf dist

echo "Deleting cluster and waiting for deletion"
aws cloudformation delete-stack --stack-name "umsi-easy-hub-${TAG}-cluster"
aws cloudformation wait stack-delete-complete --stack-name "umsi-easy-hub-${TAG}-cluster"
echo "Deleting control node and waiting for deletion"
aws cloudformation delete-stack --stack-name "umsi-easy-hub-${TAG}-control-node"
aws cloudformation wait stack-delete-complete --stack-name "umsi-easy-hub-${TAG}-control-node"


