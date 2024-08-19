import aws_cdk as cdk

from delta_upgrade_bot.delta_upgrade_bot_stack import DeltaUpgradeBotStack

app = cdk.App()
env = cdk.Environment(account="", region="us-east-1")
DeltaUpgradeBotStack(app, "DeltaUpgradeBotStack", env=env)

app.synth()
