

build-dev:
	python build_dist.py --stage=dev
	echo "dev" > dist/stage

build-prod:
	python build_dist.py --stage=prod
	echo "prod" > dist/stage

test:
	stage=$(shell cat dist/stage)

deploy:
	
	aws cloudformation create-stack --profile controlnode --stack-name "jupyterhub-$(shell cat dist/stage)" --template-body file://dist/cloudformation.yaml --capabilities CAPABILITY_NAMED_IAM