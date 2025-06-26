# ==============================================================================
# VNM AWS Health On-Call Notification System - Configuration Script
# Purpose:
# This script allows administrators to define on-call contacts and update
# the associated AWS Systems Manager Incident Manager Response Plans.
# It makes real API calls to AWS services.
# Version: 1.2
# Date: 2025-06-25
# ==============================================================================

import boto3
import json
from botocore.exceptions import ClientError

# ==============================================================================
# SECTION 1: CONFIGURATION DEFINITIONS
# ==============================================================================

# ------------------------------------------------------------------------------
# 1.1: CONTACTS DEFINITION
# ------------------------------------------------------------------------------
CONTACTS_DEFINITION = {
    "lmhung": {
        "name": "L M Hung",
        "channels": [
            {"type": "EMAIL", "address": "lmhung@vinamilk.com.vn"},
            {"type": "SMS", "address": "+84984001202"},
        ]
    },
    "dnkhanh": {
        "name": "D N Khanh",
        "channels": [
            {"type": "EMAIL", "address": "dnkhanh@vinamilk.com.vn"},
            {"type": "SMS", "address": "+84329097001"},
        ]
    },
    "ntquy": {
        "name": "N T Quy",
        "channels": [
            {"type": "EMAIL", "address": "ntquy@vinamilk.com.vn"},
            {"type": "SMS", "address": "+84934198680"},
        ]
    },
    "dvcong": {
        "name": "D V Cong",
        "channels": [
            {"type": "EMAIL", "address": "dvcong@vinamilk.com.vn"},
            {"type": "SMS", "address": "+84344353188"},
        ]
    },
    # --- Add new contacts below this line ---
}

# ------------------------------------------------------------------------------
# 1.2: RESPONSE PLAN UPDATES
# ------------------------------------------------------------------------------
RESPONSE_PLANS_TO_UPDATE = {
    "vnm-data-prod-aws-health-crictical-response": {
        "contacts_to_engage": ["lmhung", "dnkhanh"]
    },
    "vnm-data-prod-aws-health-high-response": {
        "contacts_to_engage": ["lmhung", "ntquy", "dvcong"]
    },
    # --- Add other response plans to update below this line ---
}

# ==============================================================================
# SECTION 2: AWS API FUNCTIONS
# ==============================================================================

def create_or_update_contact(ssm_contacts_client, alias, details):
    """
    Create or update a contact in AWS Systems Manager Incident Manager.
    """
    try:
        # Prepare channels for the contact plan
        plan_stages = []
        for i, channel in enumerate(details["channels"]):
            plan_stages.append({
                "DurationInMinutes": 0 if i == len(details["channels"]) - 1 else 1,
                "Targets": [{
                    "ChannelTargetInfo": {
                        "ContactChannelId": f"{alias}-{channel['type'].lower()}",
                        "RetryIntervalInMinutes": 2
                    }
                }]
            })

        # Create contact
        try:
            response = ssm_contacts_client.create_contact(
                Alias=alias,
                DisplayName=details["name"],
                Type="PERSONAL",
                Plan={
                    "Stages": plan_stages
                }
            )
            print(f"✓ Created contact: {alias}")
            contact_arn = response["ContactArn"]
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConflictException':
                # Contact already exists, get its ARN
                response = ssm_contacts_client.get_contact(
                    ContactId=alias
                )
                contact_arn = response["ContactArn"]
                print(f"✓ Contact already exists: {alias}")
            else:
                raise e

        # Create or update contact channels
        for channel in details["channels"]:
            channel_id = f"{alias}-{channel['type'].lower()}"
            try:
                ssm_contacts_client.create_contact_channel(
                    ContactId=contact_arn,
                    Name=f"{details['name']} - {channel['type']}",
                    Type=channel["type"],
                    DeliveryAddress={
                        "SimpleAddress": channel["address"]
                    }
                )
                print(f"  ✓ Created {channel['type']} channel for {alias}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ConflictException':
                    print(f"  ✓ {channel['type']} channel already exists for {alias}")
                else:
                    raise e

        return contact_arn

    except ClientError as e:
        print(f"✗ Error creating/updating contact {alias}: {e}")
        raise e

def update_response_plan(ssm_incidents_client, plan_name, plan_details, contact_arns):
    """
    Update a response plan to engage specified contacts.
    """
    try:
        # Build engagement list from contact aliases
        engagements = []
        for contact_alias in plan_details["contacts_to_engage"]:
            if contact_alias in contact_arns:
                engagements.append(contact_arns[contact_alias])

        # Get current response plan to preserve other settings
        try:
            current_plan = ssm_incidents_client.get_response_plan(
                Arn=f"arn:aws:ssm-incidents::{get_account_id()}:response-plan/{plan_name}"
            )
            
            # Update the response plan with new engagements
            ssm_incidents_client.update_response_plan(
                Arn=current_plan["Arn"],
                Engagements=engagements
            )
            print(f"✓ Updated response plan: {plan_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"✗ Response plan not found: {plan_name}")
            else:
                raise e

    except ClientError as e:
        print(f"✗ Error updating response plan {plan_name}: {e}")
        raise e

def get_account_id():
    """Get the current AWS account ID."""
    sts_client = boto3.client('sts')
    return sts_client.get_caller_identity()['Account']

def main():
    """
    Main function to process the configurations and make real AWS API calls.
    """
    print("Starting AWS Incident Manager Configuration Script...")
    
    # Initialize AWS clients
    try:
        ssm_contacts_client = boto3.client('ssm-contacts')
        ssm_incidents_client = boto3.client('ssm-incidents')
        print("✓ AWS clients initialized")
    except Exception as e:
        print(f"✗ Error initializing AWS clients: {e}")
        return

    contact_arns = {}

    # --- Step 1: Create/update contacts ---
    print("\n--- [1/2] Processing Contact Definitions ---")
    for alias, details in CONTACTS_DEFINITION.items():
        try:
            contact_arn = create_or_update_contact(ssm_contacts_client, alias, details)
            contact_arns[alias] = contact_arn
        except Exception as e:
            print(f"✗ Failed to process contact {alias}: {e}")
            continue

    print("--- Contact Definitions Processed ---\n")

    # --- Step 2: Update Response Plans ---
    print("\n--- [2/2] Processing Response Plan Updates ---")
    for plan_name, plan_details in RESPONSE_PLANS_TO_UPDATE.items():
        try:
            update_response_plan(ssm_incidents_client, plan_name, plan_details, contact_arns)
        except Exception as e:
            print(f"✗ Failed to update response plan {plan_name}: {e}")
            continue

    print("--- Response Plan Updates Processed ---\n")
    print("Script execution completed.")

if __name__ == "__main__":
    main()
