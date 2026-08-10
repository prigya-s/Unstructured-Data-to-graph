# Network Architecture Overview

This document describes the core systems, services, and data stores that make
up the enterprise network architecture.

## Core Systems

The Core Banking System uses the Customer Database to store account
information. The Core Banking System depends on the Payment Gateway API to
process transactions.

### Payment Processing

The Payment Service connects to the Payment Gateway API for authorization.
The Payment Service depends on the Fraud Detection Service to validate
transactions before they are settled.

## Data Platform

The Data Engineering Team owns the Analytics Database. The Analytics Database
contains customer transaction records used for reporting.

The Reporting Service uses the Analytics Database to generate dashboards.
The Reporting Service implements the Data Retention Policy.

## Technology Stack

The platform uses Kubernetes for orchestration and PostgreSQL for relational
storage. The Payment Service is built with Java and deployed on AWS.

Key technologies:

- Kubernetes for container orchestration
- PostgreSQL for relational data
- Kafka for event streaming

## Governance

All services must implement the Data Security Policy. The Security Team owns
the Data Security Policy and reviews it quarterly.

| System | Owning Team | Technology |
|---|---|---|
| Core Banking System | Platform Engineering Team | Java |
| Analytics Database | Data Engineering Team | PostgreSQL |
