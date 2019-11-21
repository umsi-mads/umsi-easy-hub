#!/bin/bash

if grep '^[-0-9a-zA-Z]*$' <<<$1 && [ ! -z "$1" ];
  then echo "Tag is valid";
  else echo "Tag must be alphanumeric." && exit 1;
fi

TAG=$1
echo $TAG > dist/tag

PROJECT="umsi-easy-hub"

python build_dist.py --tag=$TAG --project=$PROJECT

aws cloudformation create-stack --profile "easy-deploy-jupyterhub" --stack-name "$PROJECT-$TAG" --template-body file://dist/cloudformation.yaml --capabilities CAPABILITY_NAMED_IAM
