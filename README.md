## EMR Cost Calculator

#### Features at a glance
- Calculates exact costs of an EMR cluster (EMR + EC2 costs)
- Multiple EMR clusters cost calculation for a given period
- Spot prices and all other prices are exact and retrieved every time from AWS Pricing API
- If a cluster is still running, costs incurred up to current time are displayed

#### Why the need for this script

Given that Amazon doesn't provide a straightforward solution to calculate the cost of an EMR workflow, this module aims to calculate the cost of an EMR workflow given a period of days, or the cost of a single cluster given the cluster id. The simple way to do that would be to use the information given by the JobFLow method of the boto.emr module. However, this method doesn't return any information about the Task nodes of a cluster, and whether or not spot instances were used. This cost calculator takes care of both. OnDemand instance prices are retrieved using the AWS pricing API. In case spot instances were used, the price is retrieved using the AWS EC2 API.

### Install

To install or upgrade the package it's best to use pip:
`pip install -U aws-emr-cost-calculator`

Users with python<2.7.9 won't be able to run the code if requests[security] isn't installed (which is listed in requirements.txt)<br>
Python 3.7 is tested, lower 3x versions will probably work though.  

### How it works

This module is using [docopt](http://docopt.org/) to parse command line arguments.

It currently supports two operations:

1. Get the total cost of an EMR workflow for a given period of days
  * `aws-emr-cost-calculator total --created_after=<YYYY-MM-DD> --created_before=<YYYY-MM-DD>`

2. Get the cost of an EMR cluster given the cluster id
  * `aws-emr-cost-calculator cluster --cluster_id=<j-xxxxxxxxxxxx>`

Authentication to AWS API is done using credentials of AWS CLI which are configured by executing
`aws configure`

### License

Distributed under the MIT license. See `LICENSE` for more information.
