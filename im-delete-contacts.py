# ==============================================================================
# VNM AWS Incident Manager - Contact Deletion Script
# Purpose:
# This script allows administrators to safely delete contacts from AWS Systems
# Manager Incident Manager. It includes dry-run mode and confirmation prompts.
# Version: 1.0
# Date: 2025-06-25
# ==============================================================================

import boto3
import json
from botocore.exceptions import ClientError
from typing import Dict, List, Optional, Set

# ==============================================================================
# SECTION 1: CONFIGURATION
# ==============================================================================

# ------------------------------------------------------------------------------
# 1.1: CONTACTS TO DELETE
# ------------------------------------------------------------------------------
CONTACTS_TO_DELETE = [
    "asdasd",
    # Add more contact aliases below
    # "johndoe",
    # "janedoe",
]

# ------------------------------------------------------------------------------
# 1.2: SCRIPT CONFIGURATION
# ------------------------------------------------------------------------------
CONFIG = {
    "dry_run": False,  # IMPORTANT: Set to False to actually delete contacts
    "require_confirmation": False,  # Ask for confirmation before deletion
    "remove_from_response_plans": True,  # Remove contacts from response plans before deletion
    "aws_region": None,  # Set to specific region or None for default
    "verbose": True
}

# SAFETY NOTE: This script will permanently delete contacts when dry_run=False.
# Always test with dry_run=True first to see what will be deleted.

# ==============================================================================
# SECTION 2: AWS HELPER CLASS
# ==============================================================================

class AWSContactDeletionHelper:
    def __init__(self, region=None, dry_run=False, verbose=True):
        self.dry_run = dry_run
        self.verbose = verbose
        self.region = region
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
        """Get the current AWS account ID"""
        if self.account_id is None:
            self.account_id = self.sts_client.get_caller_identity()['Account']
        return self.account_id

    def get_contact_arn(self, alias: str) -> str:
        """Build contact ARN from alias"""
        region = self.region or boto3.Session().region_name or 'us-east-1'
        return f"arn:aws:ssm-contacts:{region}:{self.get_account_id()}:contact/{alias}"

    def get_contact_details(self, alias: str) -> Optional[Dict]:
        """Get contact details if it exists"""
        contact_arn = self.get_contact_arn(alias)
        try:
            response = self.ssm_contacts_client.get_contact(ContactId=contact_arn)
            return {
                "arn": contact_arn,
                "alias": alias,
                "name": response.get("DisplayName", alias),
                "type": response.get("Type", "PERSONAL")
            }
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return None
            else:
                raise e

    def get_contact_channels(self, contact_arn: str) -> List[Dict]:
        """Get all channels for a contact"""
        try:
            response = self.ssm_contacts_client.list_contact_channels(ContactId=contact_arn)
            channels = []
            for channel in response.get('ContactChannels', []):
                channels.append({
                    "arn": channel['ContactChannelArn'],
                    "name": channel['Name'],
                    "type": channel['Type']
                })
            return channels
        except ClientError:
            return []

    def get_response_plans_using_contact(self, contact_arn: str) -> List[str]:
        """Find all response plans that use this contact"""
        response_plans = []
        try:
            # List all response plans
            paginator = self.ssm_incidents_client.get_paginator('list_response_plans')
            for page in paginator.paginate():
                for plan_summary in page.get('responsePlanSummaries', []):
                    plan_arn = plan_summary['arn']
                    # Get full response plan details
                    plan_details = self.ssm_incidents_client.get_response_plan(arn=plan_arn)
                    
                    # Check if contact is in engagements
                    if contact_arn in plan_details.get('engagements', []):
                        response_plans.append(plan_summary['name'])
        except ClientError as e:
            self.log(f"Error listing response plans: {e}", "ERROR")
        
        return response_plans

    def remove_contact_from_response_plan(self, plan_name: str, contact_arn: str):
        """Remove a contact from a response plan"""
        if self.dry_run:
            self.log(f"[DRY RUN] Would remove contact from response plan: {plan_name}", "DEBUG")
            return

        try:
            plan_arn = f"arn:aws:ssm-incidents::{self.get_account_id()}:response-plan/{plan_name}"
            
            # Get current plan
            plan_details = self.ssm_incidents_client.get_response_plan(arn=plan_arn)
            current_engagements = plan_details.get('engagements', [])
            
            # Remove the contact
            new_engagements = [eng for eng in current_engagements if eng != contact_arn]
            
            if len(new_engagements) < len(current_engagements):
                # Update the plan
                self.ssm_incidents_client.update_response_plan(
                    arn=plan_arn,
                    engagements=new_engagements
                )
                self.log(f"Removed contact from response plan: {plan_name}")
            else:
                self.log(f"Contact not found in response plan: {plan_name}", "WARN")
                
        except ClientError as e:
            self.log(f"Error updating response plan {plan_name}: {e}", "ERROR")

    def delete_contact_channel(self, channel_arn: str, channel_info: Dict):
        """Delete a contact channel"""
        if self.dry_run:
            self.log(f"[DRY RUN] Would delete {channel_info['type']} channel: {channel_info['name']}", "DEBUG")
            return

        try:
            self.ssm_contacts_client.delete_contact_channel(ContactChannelId=channel_arn)
            self.log(f"Deleted {channel_info['type']} channel: {channel_info['name']}")
        except ClientError as e:
            self.log(f"Error deleting channel {channel_info['name']}: {e}", "ERROR")

    def delete_contact(self, alias: str):
        """Delete a contact and all its channels"""
        # Get contact details
        contact_info = self.get_contact_details(alias)
        
        if not contact_info:
            self.log(f"Contact not found: {alias}", "WARN")
            return False
        
        self.log(f"\nProcessing contact: {alias} ({contact_info['name']})")
        
        # Get contact channels
        channels = self.get_contact_channels(contact_info['arn'])
        if channels:
            self.log(f"Found {len(channels)} channel(s) for {alias}:")
            for channel in channels:
                self.log(f"  - {channel['type']}: {channel['name']}", "DEBUG")
        
        # Check response plans
        if CONFIG["remove_from_response_plans"]:
            response_plans = self.get_response_plans_using_contact(contact_info['arn'])
            if response_plans:
                self.log(f"Contact is used in {len(response_plans)} response plan(s):")
                for plan in response_plans:
                    self.log(f"  - {plan}", "DEBUG")
                
                # Remove from response plans
                for plan in response_plans:
                    self.remove_contact_from_response_plan(plan, contact_info['arn'])
        
        # Delete contact channels
        for channel in channels:
            self.delete_contact_channel(channel['arn'], channel)
        
        # Delete the contact itself
        if self.dry_run:
            self.log(f"[DRY RUN] Would delete contact: {alias}", "DEBUG")
        else:
            try:
                self.ssm_contacts_client.delete_contact(ContactId=contact_info['arn'])
                self.log(f"Deleted contact: {alias}")
            except ClientError as e:
                self.log(f"Error deleting contact {alias}: {e}", "ERROR")
                return False
        
        return True

    def print_summary(self, contacts_processed: Dict[str, bool]):
        """Print execution summary"""
        print("\n" + "="*60)
        if self.dry_run:
            print("DRY RUN SUMMARY")
        else:
            print("DELETION SUMMARY")
        print("="*60)
        
        successful = sum(1 for success in contacts_processed.values() if success)
        failed = len(contacts_processed) - successful
        
        print(f"Total contacts processed: {len(contacts_processed)}")
        print(f"  • {'Would delete' if self.dry_run else 'Deleted'}: {successful}")
        print(f"  • Failed: {failed}")
        
        if failed > 0:
            print("\nFailed deletions:")
            for alias, success in contacts_processed.items():
                if not success:
                    print(f"  • {alias}")
        
        print(f"\nConfiguration:")
        print(f"  • Mode: {'DRY RUN' if self.dry_run else 'LIVE DELETION'}")
        print(f"  • AWS Region: {self.region or 'default'}")
        print(f"  • AWS Account: {self.get_account_id()}")
        
        if self.dry_run and successful > 0:
            print("\nTo perform actual deletion:")
            print("  1. Set CONFIG['dry_run'] = False")
            print("  2. Run the script again")
        
        print("="*60)

# ==============================================================================
# SECTION 3: MAIN EXECUTION
# ==============================================================================

def confirm_deletion(contacts: List[str]) -> bool:
    """Ask for user confirmation before deletion"""
    print("\n" + "!"*60)
    print("WARNING: You are about to delete the following contacts:")
    print("!"*60)
    for contact in contacts:
        print(f"  • {contact}")
    
    print(f"\nTotal contacts to delete: {len(contacts)}")
    
    if CONFIG["dry_run"]:
        print("\n[DRY RUN MODE] No actual deletions will be performed.")
        return True
    
    print("\nThis action cannot be undone!")
    response = input("\nType 'DELETE' to confirm deletion: ")
    
    return response == "DELETE"

def main():
    """Main function to delete contacts"""
    print("AWS Incident Manager - Contact Deletion Script")
    print("Version: 1.1")
    
    if not CONTACTS_TO_DELETE:
        print("\n✗ No contacts specified for deletion.")
        print("  Edit CONTACTS_TO_DELETE in this script to specify contacts.")
        return False
    
    # Initialize helper
    try:
        helper = AWSContactDeletionHelper(
            region=CONFIG["aws_region"],
            dry_run=CONFIG["dry_run"],
            verbose=CONFIG["verbose"]
        )
        helper.log("AWS clients initialized")
    except Exception as e:
        print(f"✗ Error initializing AWS clients: {e}")
        return False
    
    if CONFIG["dry_run"]:
        print("\n" + "="*60)
        print("DRY RUN MODE ENABLED")
        print("="*60)
        print("No actual changes will be made to AWS resources.")
        print("To perform actual deletion:")
        print("  1. Set CONFIG['dry_run'] = False")
        print("  2. Run the script again")
        print("="*60 + "\n")
    
    # Confirm deletion if required
    if CONFIG["require_confirmation"] and not confirm_deletion(CONTACTS_TO_DELETE):
        helper.log("Deletion cancelled by user", "WARN")
        return False
    
    # Process deletions
    contacts_processed = {}
    
    helper.log("\nStarting contact deletion process...")
    for alias in CONTACTS_TO_DELETE:
        try:
            success = helper.delete_contact(alias)
            contacts_processed[alias] = success
        except Exception as e:
            helper.log(f"Failed to process contact {alias}: {e}", "ERROR")
            contacts_processed[alias] = False
    
    # Print summary
    helper.print_summary(contacts_processed)
    
    return all(contacts_processed.values())

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)