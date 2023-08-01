from __future__ import print_function

import boto3
from retrying import retry
import sys
import typing
import datetime
import requests
from dateutil import tz


def validate_date(date_text):
    if not date_text:
        return date_text
    try:
        return datetime.datetime.strptime(date_text, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError("Incorrect data format, should be YYYY-MM-DD")


def is_error_retriable(exception):
    """
    Use this function in order to back off only
    if error is retriable
    """
    # TODO verify if this is correct way to handle this. Haven't seen errors
    # TODO like this myself
    try:
        return exception.response["Error"]["Code"].startswith("5")
    except AttributeError:
        return False


class Ec2Instance:
    def __init__(
        self, creation_ts, termination_ts, instance_type, market_type, ebs_volumes
    ):
        # creation_ts (EMR instance group parameter) correlates to EC2 instance
        # start up time
        self.creation_ts = creation_ts
        self.termination_ts = termination_ts
        self.instance_type = instance_type
        self.market_type = market_type
        self.ebs_volumes = ebs_volumes


class InstanceGroup:
    def __init__(self, group_id, instance_type, group_type, disk_size=[]):
        self.group_id = group_id
        self.instance_type = instance_type
        self.group_type = group_type
        self.disk_size = disk_size


class Ec2EmrPricing:
    def __init__(self, region: str = None):
        if region is None:
            my_session = boto3.session.Session()
            region = my_session.region_name
        url_base = "https://pricing.us-east-1.amazonaws.com"

        index_response = requests.get(url_base + "/offers/v1.0/aws/index.json")
        index = index_response.json()

        emr_regions_response = requests.get(
            url_base + index["offers"]["ElasticMapReduce"]["currentRegionIndexUrl"]
        )
        emr_region_url = (
            url_base
            + emr_regions_response.json()["regions"][region]["currentVersionUrl"]
        )

        emr_pricing = requests.get(emr_region_url).json()
        sku_to_instance_type = {}
        for sku in emr_pricing["products"]:
            if (
                "softwareType" in emr_pricing["products"][sku]["attributes"].keys()
            ) and (emr_pricing["products"][sku]["attributes"]["softwareType"] == "EMR"):
                sku_to_instance_type[sku] = emr_pricing["products"][sku]["attributes"][
                    "instanceType"
                ]

        self.emr_prices = {}
        for sku in sku_to_instance_type.keys():
            instance_type = sku_to_instance_type.get(sku)
            sku_info = emr_pricing["terms"]["OnDemand"][sku]
            if len(sku_info) > 1:
                print(
                    "[ERROR] More than one SKU for {}".format(sku_info), file=sys.stderr
                )
                sys.exit(1)
            _, sku_info_value = sku_info.popitem()
            price_dimensions = sku_info_value["priceDimensions"]
            if len(sku_info) > 1:
                print(
                    "[ERROR] More than price dimension for {}".format(price_dimensions),
                    file=sys.stderr,
                )
                sys.exit(1)
            _, price_dimensions_value = price_dimensions.popitem()
            price = float(price_dimensions_value["pricePerUnit"]["USD"])
            self.emr_prices[instance_type] = price

        ec2_regions_response = requests.get(
            url_base + index["offers"]["AmazonEC2"]["currentRegionIndexUrl"]
        )
        ec2_region_url = (
            url_base
            + ec2_regions_response.json()["regions"][region]["currentVersionUrl"]
        )

        ec2_pricing = requests.get(ec2_region_url).json()

        ec2_sku_to_instance_type = {}
        for sku in ec2_pricing["products"]:
            try:
                attr = ec2_pricing["products"][sku]["attributes"]
                if (
                    attr["tenancy"] == "Shared"
                    and attr["operatingSystem"] == "Linux"
                    and attr["operation"] == "RunInstances"
                    and attr["capacitystatus"] == "Used"
                ):
                    ec2_sku_to_instance_type[sku] = attr["instanceType"]

            except KeyError:
                pass

        self.ec2_prices = {}
        for sku in ec2_sku_to_instance_type.keys():
            instance_type = ec2_sku_to_instance_type.get(sku)
            sku_info = ec2_pricing["terms"]["OnDemand"][sku]
            if len(sku_info) > 1:
                print(
                    "[ERROR] More than one SKU for {}".format(sku_info), file=sys.stderr
                )
                sys.exit(1)
            _, sku_info_value = sku_info.popitem()
            price_dimensions = sku_info_value["priceDimensions"]
            if len(sku_info) > 1:
                print(
                    "[ERROR] More than price dimension for {}".format(price_dimensions),
                    file=sys.stderr,
                )
                sys.exit(1)
            _, price_dimensions_value = price_dimensions.popitem()
            price = float(price_dimensions_value["pricePerUnit"]["USD"])
            if instance_type in self.ec2_prices:
                print(
                    "[ERROR] Instance price for {} already added".format(instance_type),
                    file=sys.stderr,
                )
                sys.exit(1)

            self.ec2_prices[instance_type] = price

    def get_emr_price(self, instance_type):
        return self.emr_prices[instance_type]

    def get_ec2_price(self, instance_type):
        return self.ec2_prices[instance_type]


class EmrCostCalculator:
    def __init__(self, region: str = None):
        if region is None:
            my_session = boto3.session.Session()
            region = my_session.region_name
        try:
            self.conn = boto3.client("emr", region_name=region)
        except Exception as e:
            print(
                "[ERROR] Could not establish connection with EMR API\n{}".format(e),
                file=sys.stderr,
            )
            sys.exit()

        try:
            self.spot_pricing = SpotPricing(region=region)
        except Exception as e:
            print(
                "[ERROR] Could not establish connection with EC2 API\n{}".format(e),
                file=sys.stderr,
            )
            sys.exit()

        self.ec2_emr_pricing = Ec2EmrPricing(region=region)

    def get_total_cost_by_dates(self, created_after, created_before):
        total_cost = 0
        for cluster_id in self._get_cluster_list(created_after, created_before):
            cost_dict = self.get_cluster_cost(cluster_id)
            if "TOTAL" in cost_dict:
                total_cost += cost_dict["TOTAL"]
            else:
                print(
                    "[INFO] Cluster {} has no cost associated with it".format(
                        cluster_id
                    ),
                    file=sys.stderr,
                )
        return total_cost

    @retry(
        wait_exponential_multiplier=1000,
        wait_exponential_max=7000,
        retry_on_exception=is_error_retriable,
    )
    def get_cluster_cost(
        self,
        cluster_id: str,
        start_date: typing.Optional[datetime.datetime] = None,
        end_date: typing.Optional[datetime.datetime] = None,
    ):
        """
        Joins the information from the instance groups and the instances
        in order to calculate the price of the whole cluster

        It is important that we use a back off policy in this case since Amazon
        throttles the number of API requests.
        :return: A dictionary with the total cost of the cluster and the
                individual cost of each instance group (Master, Core, Task)
        """
        cost_dict: typing.Dict[str, float] = {}
        availability_zone = self._get_availability_zone(cluster_id)

        try:
            instance_groups = self._get_instance_groups(cluster_id)

            for instance_group in instance_groups:
                for instance in self._get_instances(
                    instance_group, cluster_id, start_date, end_date
                ):
                    cost = self._get_instance_cost(instance, availability_zone)
                    group_type = instance_group.group_type
                    cost_dict.setdefault(group_type + ".EC2", 0)
                    cost_dict[group_type + ".EC2"] += cost
                    cost_dict.setdefault(group_type + ".EMR", 0)
                    hours_run = (
                        instance.termination_ts - instance.creation_ts
                    ).total_seconds() / 3600
                    emr_cost = (
                        self.ec2_emr_pricing.get_emr_price(instance.instance_type)
                        * hours_run
                    )
                    cost_dict[group_type + ".EMR"] += emr_cost
                    # ebs
                    ebs_cost = 0
                    cost_dict.setdefault(group_type + ".EBS", 0)
                    for ebs in instance_group.disk_size:
                        ebs_cost = ebs_cost + ebs["VolumeSpecification"][
                            "SizeInGB"
                        ] * 0.1 * hours_run / (24 * 30)
                    cost_dict[group_type + ".EBS"] += ebs_cost
                    cost_dict.setdefault("TOTAL", 0)
                    cost_dict["TOTAL"] += cost + emr_cost + ebs_cost
        except Exception:
            instance_fleets = self._get_instance_fleets(cluster_id)
            for instance_fleet in instance_fleets:
                for instance in self._get_instances(
                    instance_fleet, cluster_id, start_date, end_date, True
                ):
                    cost = self._get_instance_cost(instance, availability_zone)
                    if cost is None:
                        cost = 0
                    group_type = instance_fleet.group_type
                    cost_dict.setdefault(group_type + ".EC2", 0)
                    cost_dict[group_type + ".EC2"] += cost
                    cost_dict.setdefault(group_type + ".EMR", 0)
                    hours_run = (
                        instance.termination_ts - instance.creation_ts
                    ).total_seconds() / 3600
                    emr_cost = (
                        self.ec2_emr_pricing.get_emr_price(instance.instance_type)
                        * hours_run
                    )
                    cost_dict[group_type + ".EMR"] += emr_cost
                    # ebs
                    ebs_cost = 0
                    cost_dict.setdefault(group_type + ".EBS", 0)
                    for ebs in instance_fleet.disk_size:
                        ebs_cost = ebs_cost + ebs["VolumeSpecification"][
                            "SizeInGB"
                        ] * 0.1 * hours_run / (24 * 30)
                    cost_dict[group_type + ".EBS"] += ebs_cost
                    cost_dict.setdefault("TOTAL", 0)
                    cost_dict["TOTAL"] += cost + emr_cost + ebs_cost

        return cost_dict

    def _get_instance_cost(self, instance, availability_zone):
        if instance.market_type == "SPOT":
            return self.spot_pricing.get_billed_price_for_period(
                instance.instance_type,
                availability_zone,
                instance.creation_ts,
                instance.termination_ts,
            )

        elif instance.market_type == "ON_DEMAND":
            ec2_price = self.ec2_emr_pricing.get_ec2_price(instance.instance_type)
            return ec2_price * (
                (instance.termination_ts - instance.creation_ts).total_seconds() / 3600
            )

    def _get_cluster_list(self, created_after, created_before):
        """
        :return: An iterator of cluster ids for the specified dates
        """
        kwargs = {"CreatedAfter": created_after, "CreatedBefore": created_before}
        while True:
            cluster_list = self.conn.list_clusters(**kwargs)
            for cluster in cluster_list["Clusters"]:
                yield cluster["Id"]
            try:
                kwargs["Marker"] = cluster_list["Marker"]
            except KeyError:
                break

    def _get_instance_groups(self, cluster_id):
        """
        Invokes the EMR api and gets a list of the cluster's instance groups.
        :return: List of our custom InstanceGroup objects
        """
        groups = self.conn.list_instance_groups(ClusterId=cluster_id)["InstanceGroups"]
        instance_groups = []
        for group in groups:
            inst_group = InstanceGroup(
                group["Id"],
                group["InstanceType"],
                group["InstanceGroupType"],
                self._get_ebs_block_devices(group),
            )

            instance_groups.append(inst_group)
        return instance_groups

    def _get_instance_fleets(self, cluster_id):
        """
        Invokes the EMR api and gets a list of the cluster's instance fleets.
        :return: List of our custom InstanceFleet objects
        """
        fleets = self.conn.list_instance_fleets(ClusterId=cluster_id)["InstanceFleets"]
        instance_fleets = []
        for fleet in fleets:
            inst_fleet = InstanceGroup(
                fleet["Id"],
                fleet["InstanceTypeSpecifications"][0]["InstanceType"],
                fleet["InstanceFleetType"],
                self._get_ebs_block_devices(fleet["InstanceTypeSpecifications"][0]),
            )

            instance_fleets.append(inst_fleet)
        return instance_fleets

    def _get_instances(
        self,
        instance_group,
        cluster_id,
        start_date: typing.Optional[datetime.datetime],
        end_date: typing.Optional[datetime.datetime],
        fleet=False,
    ):
        """
        Invokes the EMR api to retrieve a list of all the instances
        that were used in the cluster.
        This list is then joined to the InstanceGroup list
        on the instance group id
        :return: An iterator of our custom Ec2Instance objects.
        """
        instance_list = []
        list_instances_args = {
            "ClusterId": cluster_id,
            "InstanceGroupId": instance_group.group_id,
        }
        if fleet:
            list_instances_args = {
                "ClusterId": cluster_id,
                "InstanceFleetId": instance_group.group_id,
            }
        while True:
            batch = self.conn.list_instances(**list_instances_args)
            instance_list.extend(batch["Instances"])
            try:
                list_instances_args["Marker"] = batch["Marker"]
            except KeyError:
                break
        for instance_info in instance_list:
            try:
                creation_time: datetime.datetime = instance_info["Status"]["Timeline"][
                    "CreationDateTime"
                ]
                try:
                    end_date_time = instance_info["Status"]["Timeline"]["EndDateTime"]
                except KeyError:
                    # use same TZ as one in creation time.
                    # By default datetime.now() is not TZ aware
                    end_date_time = datetime.datetime.now(tz=creation_time.tzinfo)

                if start_date and end_date:
                    start_date_tz = start_date.replace(tzinfo=tz.tzutc())
                    start_date_tz = start_date_tz.astimezone(creation_time.tzinfo)
                    end_date_tz = end_date.replace(tzinfo=tz.tzutc())
                    end_date_tz = end_date_tz.astimezone(creation_time.tzinfo)

                    if end_date_tz <= creation_time:
                        continue

                    if creation_time <= start_date_tz:
                        creation_time = start_date_tz
                    if end_date_time >= end_date_tz:
                        end_date_time = end_date_tz

                inst = Ec2Instance(
                    creation_time,
                    end_date_time,
                    instance_info["InstanceType"],
                    instance_info["Market"],
                    instance_info["EbsVolumes"],
                )
                yield inst
            except AttributeError as e:
                print(
                    "[WARN] Error when computing instance cost."
                    "Cluster: {}\n"
                    "{}".format(cluster_id, e),
                    file=sys.stderr,
                )

    def _get_ebs_block_devices(self, spec_map):
        ebsBlockDevices = []
        if "EbsBlockDevices" in spec_map:
            ebsBlockDevices = spec_map["EbsBlockDevices"]
        return ebsBlockDevices

    def _get_availability_zone(self, cluster_id):
        cluster_description = self.conn.describe_cluster(ClusterId=cluster_id)
        return cluster_description["Cluster"]["Ec2InstanceAttributes"][
            "Ec2AvailabilityZone"
        ]


class SpotPricing:
    def __init__(self, region: str = None):
        if region is None:
            my_session = boto3.session.Session()
            region = my_session.region_name
        self.all_prices = {}
        self.client_ec2 = boto3.client("ec2", region_name=region)

    def _populate_all_prices_if_needed(
        self, instance_id, availability_zone, start_time, end_time
    ):
        previous_ts = None

        if (instance_id, availability_zone) in self.all_prices:
            prices = self.all_prices[(instance_id, availability_zone)]
            if (
                end_time - sorted(prices.keys())[-1]
                < datetime.timedelta(days=1, hours=1)
                and sorted(prices.keys())[0] < start_time
            ):
                # this means we already have requested dates. Nothing to do
                return
        else:
            prices = {}

        next_token = ""
        while True:
            prices_response = self.client_ec2.describe_spot_price_history(
                InstanceTypes=[instance_id],
                ProductDescriptions=["Linux/UNIX (Amazon VPC)"],
                AvailabilityZone=availability_zone,
                StartTime=start_time,
                EndTime=end_time,
                NextToken=next_token,
            )
            for price in prices_response["SpotPriceHistory"]:
                if previous_ts is None:
                    previous_ts = price["Timestamp"]
                if previous_ts - price["Timestamp"] > datetime.timedelta(
                    days=1, hours=1
                ):
                    print(
                        "[ERROR] Expecting maximum of 1 day 1 hour difference"
                        " between spot price entries. Two dates "
                        "causing problems: {} AND {} Diff is: {}".format(
                            previous_ts,
                            price["Timestamp"],
                            previous_ts - price["Timestamp"],
                        ),
                        file=sys.stderr,
                    )
                    quit(-1)
                prices[price["Timestamp"]] = float(price["SpotPrice"])
                previous_ts = price["Timestamp"]

            next_token = prices_response["NextToken"]
            if next_token == "":
                break

        self.all_prices[(instance_id, availability_zone)] = prices

    def get_billed_price_for_period(
        self, instance_id, availability_zone, start_time, end_time
    ):
        self._populate_all_prices_if_needed(
            instance_id, availability_zone, start_time, end_time
        )

        prices = self.all_prices[(instance_id, availability_zone)]

        summed_price = 0.0
        sorted_price_timestamps = sorted(prices.keys())

        summed_until_timestamp = start_time
        for key_id in range(0, len(sorted_price_timestamps)):
            price_timestamp = sorted_price_timestamps[key_id]
            if (
                key_id == len(sorted_price_timestamps) - 1
                or end_time < sorted_price_timestamps[key_id + 1]
            ):
                # this is the last price measurement we want: add final part of
                # price segment and exit
                seconds_passed = (end_time - summed_until_timestamp).total_seconds()
                summed_price = summed_price + (
                    float(seconds_passed) * prices[price_timestamp] / 3600.0
                )
                return summed_price
            if (
                sorted_price_timestamps[key_id]
                < summed_until_timestamp
                < sorted_price_timestamps[key_id + 1]
            ):
                seconds_passed = (
                    sorted_price_timestamps[key_id + 1] - summed_until_timestamp
                ).total_seconds()
                summed_price = summed_price + (
                    float(seconds_passed) * prices[price_timestamp] / 3600.0
                )
                summed_until_timestamp = sorted_price_timestamps[key_id + 1]
