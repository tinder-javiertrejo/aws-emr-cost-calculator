from calculator.calculator import EmrCostCalculator
import boto3

my_cluster = "j-38CQ8Y8YW1H38"
profile = "tbx"

boto3.setup_default_session(profile_name=profile)
calc = EmrCostCalculator()
calculated_prices = calc.get_cluster_cost(my_cluster)
for key in sorted(calculated_prices.keys()):
    print("{:12s}: {:6.2f}".format(key, calculated_prices[key]))
