import datetime
import logging
import os
from datetime import timedelta
import boto3
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
import json
# Initialize AWS clients
try:
    ce_client = boto3.client("ce")
except Exception as e:
    logging.error("Error creating boto3 client for ce: " + str(e))
# Define the time period for cost data
cost_by_days = 30
end_date = str(datetime.datetime.now().date())
start_date = str(datetime.datetime.now().date() - timedelta(days=cost_by_days))
def cost_of_project(ce_client, start_date, end_date):
    try:
        # Fetch cost and usage data from AWS Cost Explorer
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[
                {"Type": "TAG", "Key": "Project"},  # Group by project tag
                {"Type": "DIMENSION", "Key": "SERVICE"},  # Group by resource type
            ],
        )
        # Process the response and create a dictionary to store cost data
        project_cost_data = {}
        for group in response["ResultsByTime"][0]["Groups"]:
            tag_key = group["Keys"][0]
            project_cost = group["Metrics"]["UnblendedCost"]["Amount"]
            tag_value = tag_key.split("$")[1]
            if tag_value == "":
                tag_value = "Others"
            # Extract resource information
            resource_name = group["Keys"][1]
            resource_cost = group["Metrics"]["UnblendedCost"]["Amount"]
            resource_type = resource_name.split("$")[0]
            # Store data in the dictionary
            if tag_value not in project_cost_data:
                project_cost_data[tag_value] = {"project_cost": 0.0, "resources": {}}
            project_cost_data[tag_value]["project_cost"] += float(project_cost)
            project_cost_data[tag_value]["resources"][resource_name] = {
                "resource_cost": float(resource_cost),
                "resource_type": resource_type
            }
        return project_cost_data
    except Exception as e:
        logging.error(f"Error getting cost of project: {e}")
        return None
def lambda_handler(event, context):
    try:
        # Fetch cost data
        project_cost_data = cost_of_project(ce_client, start_date, end_date)
        # Create Prometheus metrics registry
        registry = CollectorRegistry()
        # Create Prometheus Gauges for project spend and resource cost
        g_resource = Gauge(
            "Project_Resource_Cost",
            "XC3 Project Resource Cost",
            labelnames=["project_spend_project", "resource_name", "resource_cost"],
            registry=registry,
        )
        g_project = Gauge(
            "Project_Spend_Cost",
            "XC3 Project Spend Cost",
            labelnames=["project_spend_project", "project_spend_cost"],
            registry=registry,
        )
        # Iterate through project-wise cost data and populate Prometheus metrics
        for project, data in project_cost_data.items():
            g_project.labels(project, data["project_cost"]).set(data["project_cost"])
            for resource_name, resource_data in data["resources"].items():
                resource_cost = resource_data["resource_cost"]
                g_resource.labels(project, resource_name, resource_cost).set(resource_cost)
        # Convert data to JSON
        json_data = json.dumps(project_cost_data)
        # Upload data to S3 (if needed)
        # Push data to Prometheus gateway
        # Log success
        logging.info("Data has been pushed to Prometheus successfully.")
        return {"statusCode": 200, "body": json_data}
    except Exception as e:
        logging.error(f"Error executing lambda_handler: {e}")
        return "Failed to execute. Please check logs for more details."