from calculator.calculator import EmrCostCalculator
import boto3

my_cluster = "****"
profile = "***"
region = "***"

boto3.setup_default_session(profile_name=profile)
calc = EmrCostCalculator(region=region)
calculated_prices = calc.get_cluster_cost(my_cluster)
for key in sorted(calculated_prices.keys()):
    print("{:12s}: {:6.2f}".format(key, calculated_prices[key]))
