## EMR Cost Calculator

This project is a fork of [https://github.com/marko-bast/aws-emr-cost-calculator].

Original features:
- Calculates exact costs of an EMR cluster (EMR + EC2 costs)
- Multiple EMR clusters cost calculation for a given period
- Spot prices and all other prices are exact and retrieved every time from AWS Pricing API
- If a cluster is still running, costs incurred up to current time are displayed

In addition to the original project:
- calculate cost for EMR Instance Fleets
- compute cost of EBS

### Why the need for this script

Given that Amazon doesn't provide a straightforward solution to calculate the cost of an EMR workflow, this module aims to calculate the cost of an EMR workflow given a period of days, or the cost of a single cluster given the cluster id. The simple way to do that would be to use the information given by the JobFLow method of the boto.emr module. However, this method doesn't return any information about the Task nodes of a cluster, and whether or not spot instances were used. This cost calculator takes care of both. OnDemand instance prices are retrieved using the AWS pricing API. In case spot instances were used, the price is retrieved using the AWS EC2 API.

EBS cost is fixed to 0.1 $ for month.

### Install

To install or upgrade the package it's best to use pip at the root of the rep:
`pip install .`

### How it works

This module is using [docopt](http://docopt.org/) to parse command line arguments.

1. Get the cost of an EMR cluster given the cluster id and a start and end timestamp
  * `aws-emr-cost-calculator2 cluster --cluster_id=<j-xxxxxxxxxxxx> --profile=<your profile> --created_after="2024-01-28 00:00" --created_before="2024-01-28 07:01"`

### License

Distributed under the MIT license. See `LICENSE` for more information.
