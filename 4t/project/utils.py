# utils.py

import boto3
from django.conf import settings

def get_data_from_s3(bucket_name, key):
    s3 = boto3.client('s3',
                      aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                      aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)
    response = s3.get_object(Bucket=bucket_name, Key=key)
    return response['Body'].read()
