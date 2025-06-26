# AWS Incident Manager Configuration Scripts

This repository contains a suite of Python scripts designed to programmatically manage contacts and response plans in **AWS Systems Manager Incident Manager**. These tools provide a reliable and repeatable way to keep your on-call and incident response configurations up to date.

## Scripts Overview

1.  **`im-update1.py` - Create/Update Contacts and Response Plans**
    *   **Purpose**: Creates or updates on-call contacts, their engagement channels (Email, SMS, Voice), and associates them with specified response plans.
    *   **Key Feature**: Supports creating sophisticated, multi-stage engagement plans where contacts are notified at specific time intervals (e.g., engage via Email at 15 minutes, then SMS at 30 minutes).
    *   **Idempotent**: The script can be run multiple times without creating duplicate resources. It intelligently checks for existing contacts and channels before making changes.

2.  **`im-delete-contacts.py` - Delete Contacts**
    *   **Purpose**: Safely deletes contacts from Incident Manager.
    *   **Key Feature**: Automatically disassociates a contact from any response plans it belongs to before deletion, preventing orphaned resources and potential errors.
    *   **Safety First**: Includes a `dry_run` mode (enabled by default) to review what will be deleted before any changes are made.

## Prerequisites

*   **Python 3**: The scripts are written in Python 3.
*   **Boto3**: The AWS SDK for Python.
*   **AWS Credentials**: Configured AWS credentials with the necessary IAM permissions.

### IAM Permissions

The IAM role or user executing these scripts requires the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "IncidentManagerAccess",
            "Effect": "Allow",
            "Action": [
                "ssm-contacts:CreateContact",
                "ssm-contacts:GetContact",
                "ssm-contacts:UpdateContact",
                "ssm-contacts:DeleteContact",
                "ssm-contacts:CreateContactChannel",
                "ssm-contacts:ListContactChannels",
                "ssm-contacts:DeleteContactChannel",
                "ssm-incidents:Get*",
                "ssm-incidents:List*",
                "ssm-incidents:UpdateResponsePlan",
                "sts:GetCallerIdentity"
            ],
            "Resource": "*"
        }
    ]
}
```
**Note**: For enhanced security, it is best practice to restrict the `Resource` to the specific ARNs of your contacts and response plans where possible.

## Setup and Execution

1.  **Install Boto3**:
    ```sh
    pip3 install boto3
    ```

2.  **Configure AWS Credentials**:
    Ensure your environment is configured with AWS credentials, for example, by setting environment variables:
    ```sh
    export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY"
    export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_KEY"
    export AWS_REGION="your-aws-region"
    ```

### Using `im-update1.py`

1.  **Define Contacts**:
    Open `im-update1.py` and populate the `CONTACTS_DEFINITION` dictionary. Specify each contact's name, channels, and the desired `engagement_time_minutes` for each channel.

    ```python
    CONTACTS_DEFINITION = {
        "lmhung": {
            "name": "L M Hung",
            "channels": [
                {"type": "EMAIL", "address": "lmhung@example.com", "engagement_time_minutes": 0},
                {"type": "SMS", "address": "+84123456789", "engagement_time_minutes": 5},
            ]
        },
        # ... more contacts
    }
    ```

2.  **Assign to Response Plans**:
    In the `RESPONSE_PLANS_TO_UPDATE` dictionary, map your response plan names to the list of contact aliases that should be engaged.

    ```python
    RESPONSE_PLANS_TO_UPDATE = {
        "my-critical-response-plan": {
            "contacts_to_engage": ["lmhung", "dnkhanh"]
        },
        # ... more plans
    }
    ```

3.  **Configure Script Settings**:
    Review the `CONFIG` dictionary. Set `dry_run` to `True` to preview changes without applying them.

    ```python
    CONFIG = {
        "dry_run": True,
        # ... other settings
    }
    ```

4.  **Execute the Script**:
    ```sh
    python3 im-update1.py
    ```

### Using `im-delete-contacts.py`

1.  **Specify Contacts for Deletion**:
    Open `im-delete-contacts.py` and add the aliases of the contacts you wish to delete to the `CONTACTS_TO_DELETE` list.

    ```python
    CONTACTS_TO_DELETE = [
        "asdasd",
        "johndoe",
    ]
    ```

2.  **Run in Dry Run Mode (Recommended First)**:
    The script defaults to `dry_run = True`. Run it to see which contacts and associated resources will be removed.

    ```sh
    python3 im-delete-contacts.py
    ```
    The output will show a summary of actions that *would* be taken.

3.  **Perform Deletion**:
    When you are ready to permanently delete the contacts, edit the script and set `dry_run` to `False`.

    ```python
    CONFIG = {
        "dry_run": False,
        # ... other settings
    }
    ```

4.  **Execute for Real**:
    Run the script again to perform the deletion.
    ```sh
    python3 im-delete-contacts.py
    ```
