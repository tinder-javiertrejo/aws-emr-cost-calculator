## EMR Cost Calculator

#### A simple python module that calculates the cost of a single or a group of EMR clusters.

Given that Amazon doesn't provide a straightforward solution to calculate the cost of an EMR workflow, this module aims to calculate the cost of an EMR workflow given a period of days,
or the cost of a single cluster given the cluster id. The simple way to do that would be to use the information given by the JobFLow method of the boto.emr module. However, this method
doesn't return any information about the Task nodes of a cluster, and whether or not spot instances were used. This cost calculator takes care of both. OnDemand instance prices are
retrieved using AWS pricing API. In case spot instances were used, the price is retrieved using AWS EC2 API.

### How it works

This module is using [docopt](http://docopt.org/) in order to parse command line arguments.

It currently support two operations:

1. Get the total cost of an EMR workflow for a given period of days
  * `emr_cost_calculator.py total --region=<The region you launched your clusters in> --created_after=<YYYY-MM-DD> --created_before=<YYYY-MM-DD>`

2. Get the cost of an EMR cluster given the cluster id
  * `emr_cost_calculator.py cluster --region=<The region you launched your clusters in> --cluster_id=<j-xxxxxxxxxxxx>`

Authentication to AWS API is done using credentials of AWS CLI which are setup by executing
`aws configure`

Alternatively, you can provide credentials by using aws_access_key_id and the aws_secret_access_key script parameters.

Or, you can set the environment variables:

`AWS_ACCESS_KEY_ID - Your AWS Access Key ID
AWS_SECRET_ACCESS_KEY - Your AWS Secret Access Key`

### Install

To install all requirements it's best to use
`pip install -r requirements.txt`

Users with python<2.7.9 won't be able to run the code if requests[security] isn't installed (which is listed in requirements.txt)

### License

Distributed under the MIT license. See `LICENSE` for more information.
