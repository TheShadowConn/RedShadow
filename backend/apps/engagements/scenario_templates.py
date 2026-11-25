# ruff: noqa: E501  (descriptions are prose data)
"""Starter scenario lists. Plain data in code: no database rows, nothing to migrate. Each item is one scenario
(name and description); applying a template creates them as planned scenarios, skipping names already present."""

TEMPLATES = [
    {
        "key": "owasp_top10_2021",
        "name": "OWASP Top 10 (2021), web applications",
        "items": [
            (
                "A01: Broken Access Control",
                "Check that users cannot act outside their permissions: direct object references, missing function-level checks, forced browsing, privilege escalation, CORS misconfiguration.",
            ),
            (
                "A02: Cryptographic Failures",
                "Check data in transit and at rest: weak or missing TLS, weak algorithms, hard-coded or reused keys, sensitive data exposed in responses, URLs or backups.",
            ),
            (
                "A03: Injection",
                "Test every input for SQL, NoSQL, OS command, LDAP and template injection, and for cross-site scripting.",
            ),
            (
                "A04: Insecure Design",
                "Review business logic and abuse cases: missing rate limits, flawed workflows, trust boundaries, missing threat modelling.",
            ),
            (
                "A05: Security Misconfiguration",
                "Check default accounts, verbose errors, open admin interfaces, missing security headers, unnecessary features and cloud storage permissions.",
            ),
            (
                "A06: Vulnerable and Outdated Components",
                "Identify framework, library and server versions and match them against known vulnerabilities.",
            ),
            (
                "A07: Identification and Authentication Failures",
                "Test login, password reset, MFA, session handling, credential stuffing resistance and session fixation.",
            ),
            (
                "A08: Software and Data Integrity Failures",
                "Check insecure deserialization, unsigned updates, unverified CI/CD pipelines and untrusted third-party scripts.",
            ),
            (
                "A09: Security Logging and Monitoring Failures",
                "Check that logins, access failures and high-value actions are logged and that logs are protected and monitored.",
            ),
            (
                "A10: Server-Side Request Forgery",
                "Test features that fetch remote resources for access to internal services, metadata endpoints and local files.",
            ),
        ],
    },
    {
        "key": "owasp_api_top10_2023",
        "name": "OWASP API Security Top 10 (2023)",
        "items": [
            (
                "API1: Broken Object Level Authorization",
                "Swap object identifiers between users and tenants on every endpoint that takes an ID.",
            ),
            (
                "API2: Broken Authentication",
                "Test token handling, key and password reset flows, brute-force protection and weak or missing authentication.",
            ),
            (
                "API3: Broken Object Property Level Authorization",
                "Check for excessive data exposure and for mass assignment of properties the caller should not set.",
            ),
            (
                "API4: Unrestricted Resource Consumption",
                "Test rate limits, payload and page sizes, expensive queries and upload limits.",
            ),
            (
                "API5: Broken Function Level Authorization",
                "Call administrative and privileged endpoints and methods as a normal user.",
            ),
            (
                "API6: Unrestricted Access to Sensitive Business Flows",
                "Abuse flows such as purchasing, booking or sign-up with automation.",
            ),
            ("API7: Server Side Request Forgery", "Test endpoints that accept URLs for access to internal resources."),
            (
                "API8: Security Misconfiguration",
                "Check CORS, headers, verbose errors, unused methods and default settings.",
            ),
            (
                "API9: Improper Inventory Management",
                "Find old versions, undocumented and debug endpoints and exposed non-production hosts.",
            ),
            (
                "API10: Unsafe Consumption of APIs",
                "Check how the API trusts and validates data from third-party services.",
            ),
        ],
    },
    {
        "key": "owasp_mobile_top10_2024",
        "name": "OWASP Mobile Top 10 (2024)",
        "items": [
            (
                "M1: Improper Credential Usage",
                "Look for hard-coded credentials and insecure storage or transmission of keys and tokens.",
            ),
            ("M2: Inadequate Supply Chain Security", "Review third-party SDKs, build pipeline and update integrity."),
            (
                "M3: Insecure Authentication/Authorization",
                "Test local and server-side authentication and authorization, including offline and biometric flows.",
            ),
            (
                "M4: Insufficient Input/Output Validation",
                "Test deep links, intents, WebViews and server responses for injection and unsafe handling.",
            ),
            ("M5: Insecure Communication", "Check TLS use, certificate validation and pinning, and cleartext traffic."),
            ("M6: Inadequate Privacy Controls", "Check what personal data is collected, logged, shared or exposed."),
            (
                "M7: Insufficient Binary Protections",
                "Check obfuscation, tamper and root or jailbreak detection, and reverse-engineering resistance.",
            ),
            (
                "M8: Security Misconfiguration",
                "Review manifest or plist settings, exported components, backups and debug flags.",
            ),
            ("M9: Insecure Data Storage", "Inspect local storage, caches, logs, keychain or keystore use and backups."),
            (
                "M10: Insufficient Cryptography",
                "Check algorithms, key management, randomness and implementation errors.",
            ),
        ],
    },
    {
        "key": "internal_network",
        "name": "Internal network starter",
        "items": [
            (
                "Network discovery and enumeration",
                "Identify live hosts, open services, versions and network segmentation.",
            ),
            ("Active Directory enumeration", "Map users, groups, trusts, delegation and misconfigured permissions."),
            ("Credential attacks", "Test password policy, spraying, hash capture and relay, and credential reuse."),
            ("Privilege escalation", "Look for local and domain privilege escalation paths."),
            ("Lateral movement", "Test how far one compromised host or account can reach."),
            ("Sensitive data exposure", "Search file shares, databases and backups for sensitive data and secrets."),
        ],
    },
    {
        "key": "cloud_review",
        "name": "Cloud configuration starter",
        "items": [
            ("Identity and access management", "Review roles, policies, keys, MFA and over-privileged identities."),
            ("Storage exposure", "Check buckets and blobs for public access and missing encryption."),
            ("Network exposure", "Review security groups, firewalls, public endpoints and segmentation."),
            ("Secrets and key management", "Look for secrets in code, images, variables and metadata services."),
            ("Logging and monitoring", "Check that audit logs are enabled, retained and alerted on."),
            (
                "Compute and container hardening",
                "Review images, orchestration settings, patching and runtime permissions.",
            ),
        ],
    },
]
BY_KEY = {t["key"]: t for t in TEMPLATES}


def listing() -> list[dict]:
    return [
        {
            "key": t["key"], "name": t["name"],
            "items": [{"index": i, "name": n, "description": d} for i, (n, d) in enumerate(t["items"])],
        }
        for t in TEMPLATES
    ]  # fmt: skip
