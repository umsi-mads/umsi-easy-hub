

build-dev:
	python build_dist.py --stage=dev
	echo "dev" > dist/stage

build-prod:
	python build_dist.py --stage=prod
	echo "prod" > dist/stage

test:
	stage=$(shell cat dist/stage)

deploy:
	
	aws cloudformation create-stack --profile "easy-deploy-jupyterhub" --stack-name "easy-deploy-jupyterhub-$(shell cat dist/stage)" --template-body file://dist/cloudformation.yaml --capabilities CAPABILITY_NAMED_IAM

clean:
	aws ec2 delete-key-pair --key-name "easy-deploy-jupyterhub-$(shell cat dist/stage)"
	#aws iam delete-role --role-name "easy-deploy-jupyterhub-role-$(shell cat dist/stage)"
	rm "easy-deploy-jupyterhub-$(shell cat dist/stage).pem"
	# rm -rf dist
	# aws cloudformation delete-stack --stack-name "jupyterhub-$(shell cat dist/stage)"