import os

import aws_cdk as cdk
from dotenv import load_dotenv

from delta_upgrade_bot.delta_upgrade_bot_stack import DeltaUpgradeBotStack

load_dotenv()

app = cdk.App()
env = cdk.Environment(account=os.environ["CDK_DEFAULT_ACCOUNT"], region=os.environ["CDK_DEFAULT_REGION"])
DeltaUpgradeBotStack(app, "DeltaUpgradeBotStack", env=env)

app.synth()
