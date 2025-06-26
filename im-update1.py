# ==============================================================================
# VNM AWS Health On-Call Notification System - Configuration Script
# Purpose:
# This script allows administrators to define on-call contacts and update
# the associated AWS Systems Manager Incident Manager Response Plans.
# It makes real API calls to AWS services.
# Version: 2.0 - Comprehensive Debugging for Engagement Time Tracking
# Date: 2025-06-25
# ==============================================================================

import boto3
import json
import time
from botocore.exceptions import ClientError
from typing import Dict, List, Optional

# ==============================================================================
# SECTION 1: CONFIGURATION DEFINITIONS
# ==============================================================================

# ------------------------------------------------------------------------------
# 1.1: CONTACTS DEFINITION WITH ENGAGEMENT TIMING
# ------------------------------------------------------------------------------
CONTACTS_DEFINITION = {
    "lmhung": {
        "name": "L M Hung",
        "channels": [
            {"type": "EMAIL", "address": "lmhung@vinamilk.com.vn", "engagement_time_minutes": 15},
            {"type": "SMS", "address": "+84984001202", "engagement_time_minutes": 15},
        ]
    },
    "dnkhanh": {
        "name": "D N Khanh",
        "channels": [
            {"type": "EMAIL", "address": "dnkhanh@vinamilk.com.vn", "engagement_time_minutes": 15},
            {"type": "SMS", "address": "+84329097001", "engagement_time_minutes": 15},
        ]
    },
    "ntquy": {
        "name": "N T Quy",
        "channels": [
            {"type": "EMAIL", "address": "ntquy@vinamilk.com.vn", "engagement_time_minutes": 15},
            {"type": "SMS", "address": "+84934198680", "engagement_time_minutes": 15},
        ]
    },
    "dvcong": {
        "name": "D V Cong",
        "channels": [
            {"type": "EMAIL", "address": "dvcong@vinamilk.com.vn", "engagement_time_minutes": 10},
            {"type": "SMS", "address": "+84344353188", "engagement_time_minutes": 15},
        ]
    },
    # --- Add new contacts below this line ---
    # "johndoe": {
    #     "name": "John Doe",
    #     "channels": [
    #         {"type": "EMAIL", "address": "john.doe@example.com", "engagement_time_minutes": 0},
    #         {"type": "SMS", "address": "+1234567890", "engagement_time_minutes": 3},
    #         {"type": "VOICE", "address": "+1234567890", "engagement_time_minutes": 10}
    #     ]
    # }
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

# ------------------------------------------------------------------------------
# 1.3: SCRIPT CONFIGURATION
# ------------------------------------------------------------------------------
CONFIG = {
    "dry_run": False,  # Set to True to see what would be done without making changes
    "retry_attempts": 3,
    "retry_delay": 2,  # seconds
    "aws_region": None,  # Set to specific region or None for default
    "verbose": True
}

# ==============================================================================
# SECTION 2: ENHANCED AWS API FUNCTIONS
# ==============================================================================

class AWSIncidentManagerHelper:
    def __init__(self, region=None, dry_run=False, verbose=True):
        self.dry_run = dry_run
        self.verbose = verbose
        self.region = region
        # Always initialize AWS clients for real API calls
        self.ssm_contacts_client = boto3.client('ssm-contacts', region_name=region)
        self.ssm_incidents_client = boto3.client('ssm-incidents', region_name=region)
        self.sts_client = boto3.client('sts', region_name=region)
        self.account_id = None

    def log(self, message: str, level: str = "INFO"):
        """Enhanced logging with levels"""
        if not self.verbose and level == "DEBUG":
            return
        prefix = {
            "INFO": "✓",
            "WARN": "!",
            "ERROR": "✗",
            "DEBUG": "→"
        }.get(level, "•")
        print(f"{prefix} {message}")

    def get_account_id(self) -> str:
        """Get the current AWS account ID with caching"""
        if self.account_id is None:
            self.account_id = self.sts_client.get_caller_identity()['Account']
        return self.account_id

    def get_contact_arn(self, alias: str) -> str:
        """Build contact ARN from alias"""
        region = self.region or boto3.Session().region_name or 'us-east-1'
        return f"arn:aws:ssm-contacts:{region}:{self.get_account_id()}:contact/{alias}"

    def retry_operation(self, operation, *args, **kwargs):
        """Retry wrapper for AWS operations"""
        for attempt in range(CONFIG["retry_attempts"]):
            try:
                return operation(*args, **kwargs)
            except ClientError as e:
                if attempt == CONFIG["retry_attempts"] - 1:
                    raise e
                self.log(f"Attempt {attempt + 1} failed, retrying in {CONFIG['retry_delay']}s: {e}", "WARN")
                time.sleep(CONFIG["retry_delay"])

    def contact_exists(self, alias: str) -> tuple[bool, Optional[str]]:
        """Check if contact exists and return (exists, contact_arn)"""
        contact_arn = self.get_contact_arn(alias)
        if self.dry_run:
            self.log(f"[DRY RUN] Would check if contact exists: {alias}", "DEBUG")
            return False, contact_arn

        try:
            response = self.ssm_contacts_client.get_contact(ContactId=contact_arn)
            return True, contact_arn
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return False, contact_arn
            else:
                # Re-raise other errors
                raise e

    def get_existing_contact_channels(self, contact_arn: str) -> Dict[str, str]:
        """Get existing contact channels and return type->ARN mapping"""
        if self.dry_run:
            self.log(f"[DRY RUN] Would list contact channels for {contact_arn}", "DEBUG")
            return {}

        try:
            response = self.ssm_contacts_client.list_contact_channels(ContactId=contact_arn)
            return {channel['Type']: channel['ContactChannelArn'] for channel in response['ContactChannels']}
        except ClientError:
            return {}

    def create_contact_channel(self, contact_arn: str, channel_config: dict, contact_name: str) -> Optional[str]:
        """Create a contact channel and return its ARN"""
        channel_type = channel_config["type"]
        channel_address = channel_config["address"]
        
        if self.dry_run:
            self.log(f"[DRY RUN] Would create {channel_type} channel for {contact_name}: {channel_address}", "DEBUG")
            return None

        try:
            response = self.retry_operation(
                self.ssm_contacts_client.create_contact_channel,
                ContactId=contact_arn,
                Name=f"{contact_name} - {channel_type}",
                Type=channel_type,
                DeliveryAddress={"SimpleAddress": channel_address}
            )
            self.log(f"Created {channel_type} channel for {contact_name}")
            return response["ContactChannelArn"]
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConflictException':
                self.log(f"{channel_type} channel already exists for {contact_name}")
                # Get existing channel ARN
                existing_channels = self.get_existing_contact_channels(contact_arn)
                return existing_channels.get(channel_type)
            else:
                self.log(f"Error creating {channel_type} channel for {contact_name}: {e}", "ERROR")
                raise e

    def create_or_update_contact(self, alias: str, details: dict) -> Optional[str]:
        """Create or update a contact in AWS Systems Manager Incident Manager"""
        try:
            if self.dry_run:
                contact_arn = self.get_contact_arn(alias)
                self.log(f"[DRY RUN] Would create/update contact: {alias}", "DEBUG")
                return contact_arn

            # Step 1: Check if contact already exists
            existing_contact, contact_arn = self.contact_exists(alias)
            
            if existing_contact:
                self.log(f"Contact already exists: {alias}")
            else:
                # Create contact with empty plan first
                response = self.retry_operation(
                    self.ssm_contacts_client.create_contact,
                    Alias=alias,
                    DisplayName=details["name"],
                    Type="PERSONAL",
                    Plan={"Stages": []}  # Add this required parameter
                )
                contact_arn = response["ContactArn"]
                self.log(f"Created contact: {alias}")

            # Step 2: Handle contact channels
            # FIXED: Track channel ARNs with their types to ensure proper matching
            channel_arns_by_type = {}
            
            if existing_contact:
                # Get existing channels
                existing_channels = self.get_existing_contact_channels(contact_arn)
                for channel_config in details["channels"]:
                    channel_type = channel_config["type"]
                    if channel_type in existing_channels:
                        channel_arns_by_type[channel_type] = existing_channels[channel_type]
                        self.log(f"Using existing {channel_type} channel for {alias}")
                    else:
                        # Create missing channel
                        channel_arn = self.create_contact_channel(contact_arn, channel_config, details["name"])
                        if channel_arn:
                            channel_arns_by_type[channel_type] = channel_arn
            else:
                # Create all channels for new contact
                for channel_config in details["channels"]:
                    channel_type = channel_config["type"]
                    channel_arn = self.create_contact_channel(contact_arn, channel_config, details["name"])
                    if channel_arn:
                        channel_arns_by_type[channel_type] = channel_arn

            # Step 3: Create/update contact plan with proper channel ARNs and engagement timing
            if channel_arns_by_type:
                # Log raw channel configuration from input
                self.log(f"Raw channel configuration from CONTACTS_DEFINITION for {alias}:", "DEBUG")
                for i, ch_config in enumerate(details["channels"]):
                    self.log(f"  - Channel {i}: {ch_config['type']}: engagement_time_minutes = {ch_config.get('engagement_time_minutes', 'NOT_SET')}", "DEBUG")
                    self.log(f"    Full config: {ch_config}", "DEBUG")
                
                # Log channel ARN mapping
                self.log(f"Channel ARN mapping for {alias}:", "DEBUG")
                for ch_type, arn in channel_arns_by_type.items():
                    self.log(f"  - {ch_type}: {arn}", "DEBUG")
                
                # CORRECTED LOGIC: Create engagement plan based on the "engage-then-wait" model.
                plan_stages = []
                
                # Create a list of channels with their engagement times
                channel_info = []
                for channel_config in details["channels"]:
                    channel_type = channel_config["type"]
                    if channel_type in channel_arns_by_type:
                        channel_info.append({
                            "arn": channel_arns_by_type[channel_type],
                            "engagement_time": channel_config.get("engagement_time_minutes", 0),
                            "type": channel_type
                        })

                # Group channels by engagement time
                engagement_groups = {}
                for channel in channel_info:
                    engagement_time = channel["engagement_time"]
                    if engagement_time not in engagement_groups:
                        engagement_groups[engagement_time] = []
                    engagement_groups[engagement_time].append(channel)
                
                # Sort engagement times
                sorted_engagement_times = sorted(engagement_groups.keys())
                
                self.log(f"Generating corrected engagement plan for {alias}:", "DEBUG")
                
                # If the first engagement is not at T=0, create an initial wait stage with no targets.
                if sorted_engagement_times and sorted_engagement_times[0] > 0:
                    initial_wait_duration = sorted_engagement_times[0]
                    plan_stages.append({
                        "DurationInMinutes": initial_wait_duration,
                        "Targets": []
                    })
                    self.log(f"  - Stage 1: Initial wait of {initial_wait_duration} min (no engagement).", "DEBUG")

                # Create a stage for each engagement time group.
                for i, engagement_time in enumerate(sorted_engagement_times):
                    # The duration of this stage is the wait time until the *next* engagement.
                    # The final stage must have a duration > 0.
                    next_engagement_time = sorted_engagement_times[i + 1] if i + 1 < len(sorted_engagement_times) else None
                    if next_engagement_time is not None:
                        duration = next_engagement_time - engagement_time
                    else:
                        # Per AWS API rules, the last stage's duration must be positive.
                        duration = 1
                    
                    # Get all targets for the current engagement time.
                    targets = []
                    channels_at_this_time = engagement_groups[engagement_time]
                    for channel in channels_at_this_time:
                        targets.append({
                            "ChannelTargetInfo": {
                                "ContactChannelId": channel["arn"],
                                "RetryIntervalInMinutes": 2
                            }
                        })
                    
                    # Create the stage with the calculated duration and targets.
                    stage = {
                        "DurationInMinutes": duration,
                        "Targets": targets
                    }
                    plan_stages.append(stage)
                    
                    channel_types = [ch["type"] for ch in channels_at_this_time]
                    self.log(f"  - Stage {len(plan_stages)}: Engages {', '.join(channel_types)} at T={engagement_time}min. Waits {duration} min before next stage.", "DEBUG")

                # Log the final plan before sending to AWS
                self.log(f"Final engagement plan for {alias} ({len(plan_stages)} stages):", "DEBUG")
                for i, stage in enumerate(plan_stages):
                    self.log(f"  Stage {i+1}: DurationInMinutes={stage['DurationInMinutes']}, Targets={len(stage['Targets'])}", "DEBUG")
                
                try:
                    self.retry_operation(
                        self.ssm_contacts_client.update_contact,
                        ContactId=contact_arn,
                        Plan={"Stages": plan_stages}
                    )
                    self.log(f"Updated contact plan for {alias} with {len(plan_stages)} engagement stage(s)")
                    
                    # Log the engagement plan details for debugging
                    cumulative_time = 0
                    for i, (engagement_time, stage) in enumerate(zip(sorted_engagement_times, plan_stages)):
                        cumulative_time += stage["DurationInMinutes"]
                        channels_at_time = engagement_groups[engagement_time]
                        channel_types = [ch["type"] for ch in channels_at_time]
                        self.log(f"  Stage {i+1}: {', '.join(channel_types)} - Wait {stage['DurationInMinutes']} min, engage at {cumulative_time} min total", "DEBUG")
                        
                except ClientError as e:
                    self.log(f"Warning: Could not update contact plan for {alias}: {e}", "WARN")
                    # Even if plan update fails, we still have the contact and channels
            else:
                self.log(f"No channels available for {alias}, contact created without plan", "WARN")

            return contact_arn

        except ClientError as e:
            self.log(f"Error creating/updating contact {alias}: {e}", "ERROR")
            raise e

    def get_response_plan_arn(self, plan_name: str) -> str:
        """Build response plan ARN"""
        return f"arn:aws:ssm-incidents::{self.get_account_id()}:response-plan/{plan_name}"

    def update_response_plan(self, plan_name: str, plan_details: dict, contact_arns: Dict[str, str]):
        """Update a response plan to engage specified contacts"""
        try:
            # Build engagement list from contact aliases
            engagements = []
            for contact_alias in plan_details["contacts_to_engage"]:
                if contact_alias in contact_arns:
                    engagements.append(contact_arns[contact_alias])
                else:
                    self.log(f"Contact alias '{contact_alias}' not found in created contacts", "WARN")

            if not engagements:
                self.log(f"No valid contacts found for response plan {plan_name}", "WARN")
                return

            plan_arn = self.get_response_plan_arn(plan_name)

            if self.dry_run:
                self.log(f"[DRY RUN] Would update response plan: {plan_name} with {len(engagements)} contacts", "DEBUG")
                return

            # Get current response plan to ensure it exists
            try:
                current_plan = self.ssm_incidents_client.get_response_plan(arn=plan_arn)
                self.log(f"Found existing response plan: {plan_name}", "DEBUG")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    self.log(f"Response plan not found: {plan_name}", "ERROR")
                    return
                else:
                    raise e

            # Update the response plan with new engagements
            self.retry_operation(
                self.ssm_incidents_client.update_response_plan,
                arn=plan_arn,
                engagements=engagements
            )
            self.log(f"Updated response plan: {plan_name} with {len(engagements)} contact(s)")

        except ClientError as e:
            self.log(f"Error updating response plan {plan_name}: {e}", "ERROR")
            raise e

    def validate_configuration(self) -> bool:
        """Validate the configuration before processing"""
        self.log("Validating configuration...", "DEBUG")
        
        # Validate contacts
        for alias, details in CONTACTS_DEFINITION.items():
            if not alias or not isinstance(alias, str):
                self.log(f"Invalid contact alias: {alias}", "ERROR")
                return False
                
            if not details.get("name"):
                self.log(f"Contact {alias} missing name", "ERROR")
                return False
                
            if not details.get("channels") or not isinstance(details["channels"], list):
                self.log(f"Contact {alias} missing or invalid channels", "ERROR")
                return False
                
            for channel in details["channels"]:
                if not channel.get("type") or channel["type"] not in ["EMAIL", "SMS", "VOICE"]:
                    self.log(f"Contact {alias} has invalid channel type: {channel.get('type')}", "ERROR")
                    return False
                    
                if not channel.get("address"):
                    self.log(f"Contact {alias} has channel without address", "ERROR")
                    return False
                    
                # Validate engagement time
                engagement_time = channel.get("engagement_time_minutes", 0)
                if not isinstance(engagement_time, (int, float)) or engagement_time < 0:
                    self.log(f"Contact {alias} has invalid engagement_time_minutes: {engagement_time}", "ERROR")
                    return False

        # Validate response plans
        for plan_name, plan_details in RESPONSE_PLANS_TO_UPDATE.items():
            if not plan_name:
                self.log("Empty response plan name found", "ERROR")
                return False
                
            contacts_to_engage = plan_details.get("contacts_to_engage", [])
            if not contacts_to_engage:
                self.log(f"Response plan {plan_name} has no contacts to engage", "ERROR")
                return False
                
            for contact_alias in contacts_to_engage:
                if contact_alias not in CONTACTS_DEFINITION:
                    self.log(f"Response plan {plan_name} references undefined contact: {contact_alias}", "ERROR")
                    return False

        self.log("Configuration validation passed")
        return True

    def print_summary(self, contact_arns: Dict[str, str]):
        """Print execution summary"""
        print("\n" + "="*60)
        print("EXECUTION SUMMARY")
        print("="*60)
        print(f"Contacts processed: {len(contact_arns)}")
        for alias, arn in contact_arns.items():
            contact_details = CONTACTS_DEFINITION[alias]
            engagement_times = [ch.get("engagement_time_minutes", 0) for ch in contact_details["channels"]]
            print(f" • {alias} ({contact_details['name']}) - {len(contact_details['channels'])} channel(s)")
            print(f"   Engagement times: {engagement_times} minutes")

        print(f"\nResponse plans to update: {len(RESPONSE_PLANS_TO_UPDATE)}")
        for plan_name, plan_details in RESPONSE_PLANS_TO_UPDATE.items():
            print(f" • {plan_name} - {len(plan_details['contacts_to_engage'])} contact(s)")

        print(f"\nConfiguration:")
        print(f" • Dry run: {CONFIG['dry_run']}")
        print(f" • AWS Region: {self.region or 'default'}")
        print(f" • AWS Account: {self.get_account_id()}")
        print("="*60)

# ==============================================================================
# SECTION 3: MAIN EXECUTION
# ==============================================================================

def main():
    """Main function to process the configurations and make real AWS API calls"""
    print("Starting AWS Incident Manager Configuration Script...")

    # Initialize helper
    try:
        helper = AWSIncidentManagerHelper(
            region=CONFIG["aws_region"],
            dry_run=CONFIG["dry_run"],
            verbose=CONFIG["verbose"]
        )
        helper.log("AWS clients initialized")
    except Exception as e:
        print(f"✗ Error initializing AWS clients: {e}")
        return False

    # Validate configuration
    if not helper.validate_configuration():
        helper.log("Configuration validation failed. Exiting.", "ERROR")
        return False

    if CONFIG["dry_run"]:
        helper.log("Running in DRY RUN mode - no changes will be made", "WARN")

    contact_arns = {}
    success = True

    # Step 1: Create/update contacts
    helper.log("\n--- [1/2] Processing Contact Definitions ---")
    for alias, details in CONTACTS_DEFINITION.items():
        try:
            contact_arn = helper.create_or_update_contact(alias, details)
            if contact_arn:
                contact_arns[alias] = contact_arn
        except Exception as e:
            helper.log(f"Failed to process contact {alias}: {e}", "ERROR")
            success = False
            continue

    helper.log("--- Contact Definitions Processed ---")

    # Step 2: Update Response Plans
    helper.log("\n--- [2/2] Processing Response Plan Updates ---")
    for plan_name, plan_details in RESPONSE_PLANS_TO_UPDATE.items():
        try:
            helper.update_response_plan(plan_name, plan_details, contact_arns)
        except Exception as e:
            helper.log(f"Failed to update response plan {plan_name}: {e}", "ERROR")
            success = False
            continue

    helper.log("--- Response Plan Updates Processed ---")

    # Print summary
    helper.print_summary(contact_arns)

    status = "completed successfully" if success else "completed with errors"
    helper.log(f"\nScript execution {status}.")
    return success

if __name__ == "__main__":
    main()