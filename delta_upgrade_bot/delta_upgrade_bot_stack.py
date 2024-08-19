import os

from aws_cdk import (
    BundlingOptions,
    Duration,
    Stack,
    aws_lambda as lambda_,
    aws_events_targets as targets,
    aws_events as events,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
    aws_ec2 as ec2,
)
from constructs import Construct


class DeltaUpgradeBotStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        name = "DeltaUpgradeBot"

        # Network
        vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)
        subnet = vpc.select_subnets(subnet_type=ec2.SubnetType.PUBLIC).subnets[0]
        sg = ec2.SecurityGroup.from_lookup_by_name(self, "SecurityGroup", security_group_name="default", vpc=vpc)

        # Bucket
        bucket = s3.Bucket(self, name)
        s3_deployment.BucketDeployment(self, "DeployConfig", destination_bucket=bucket,
                                       sources=[s3_deployment.Source.asset('delta_upgrade_bot/bucket')])

        # SNS
        topic = sns.Topic(self, f"{name}Email")
        topic.add_subscription(sns_subscriptions.EmailSubscription(os.environ["CDK_SNS_EMAIL"]))

        lambda_fn = lambda_.Function(
            self,
            f"{name}Lambda",
            memory_size=512,
            function_name=name,
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
            timeout=Duration.minutes(5),
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

        bucket.grant_read(lambda_fn)

        rule = events.Rule(
            self,
            f"{name}Rule",
            schedule=events.Schedule.rate(Duration.minutes(30)),
        )
        rule.add_target(targets.LambdaFunction(lambda_fn))

        topic.grant_publish(lambda_fn)
