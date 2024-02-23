from aws_cdk import (
    BundlingOptions,
    Duration,
    Stack,
    aws_lambda as lambda_,
    aws_events_targets as targets,
    aws_events as events,
    aws_sns as sns,
    aws_s3 as s3,
    aws_ec2 as ec2,
)
from constructs import Construct


class DeltaUpgradeBotStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)
        subnet = ec2.Subnet.from_subnet_attributes(
            self, "Subnet", subnet_id="subnet-8d9bf8a3", availability_zone="us-east-1a"
        )
        sg = ec2.SecurityGroup.from_security_group_id(
            self, "SG", "sg-053b4fa90fb7c2679"
        )

        bucket = s3.Bucket.from_bucket_arn(
            self, "Bucket", "arn:aws:s3:::delta-upgrade-bot"
        )
        topic = sns.Topic.from_topic_arn(
            self, "Topic", "arn:aws:sns:us-east-1:872007107449:email_me"
        )

        lambdaFn = lambda_.Function(
            self,
            "Lambda",
            memory_size=512,
            function_name="DeltaUpgradeBot",
            code=lambda_.Code.from_asset(
                "./lambda",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            handler="handler.main",
            timeout=Duration.minutes(1),
            runtime=lambda_.Runtime.PYTHON_3_9,
            environment={
                "TOPIC_ARN": topic.topic_arn,
                "BUCKET_NAME": bucket.bucket_name,
                "CONFIG_FILENAME": "config.json",
            },
            vpc=vpc,
            vpc_subnets={"subnets": [subnet]},
            security_groups=[sg],
            allow_public_subnet=True,
        )

        bucket.grant_read(lambdaFn)

        rule = events.Rule(
            self,
            "Rule",
            schedule=events.Schedule.rate(Duration.hours(1)),
        )
        rule.add_target(targets.LambdaFunction(lambdaFn))

        topic.grant_publish(lambdaFn)
