"""Typed registry of SpiderFoot event types.

This module is the single source of truth for what event types exist,
their human descriptions, their category, and whether they are raw
data. The SQLite ``tbl_event_types`` table is populated from
``EVENT_TYPES`` at database initialization in ``spiderfoot/db.py``.

Adding a new event type: add an ``EventType`` enum member *and* a
matching ``EVENT_TYPES`` entry. The invariant tests in
``test/unit/spiderfoot/test_event_types.py`` will fail if the two
drift apart.
"""
import enum
from collections.abc import Callable
from dataclasses import dataclass


class EventTypeCategory(enum.Enum):
    DATA = "DATA"
    DESCRIPTOR = "DESCRIPTOR"
    ENTITY = "ENTITY"
    INTERNAL = "INTERNAL"
    SUBENTITY = "SUBENTITY"


@dataclass(frozen=True, slots=True)
class EventTypeDef:
    name: str
    description: str
    category: EventTypeCategory
    is_raw: bool
    validator: Callable[[str], bool] | None = None


class EventType(str, enum.Enum):
    # Override str() to return the raw value (Python 3.11 changed the
    # default str-mixin behaviour to return "EventType.NAME"; Task 3's
    # asDict() byte-compatibility and the invariant tests both rely on
    # str(EventType.X) == "X").
    def __str__(self) -> str:
        return self.value

    ROOT = "ROOT"
    ACCOUNT_EXTERNAL_OWNED = "ACCOUNT_EXTERNAL_OWNED"
    ACCOUNT_EXTERNAL_OWNED_COMPROMISED = "ACCOUNT_EXTERNAL_OWNED_COMPROMISED"
    ACCOUNT_EXTERNAL_USER_SHARED_COMPROMISED = "ACCOUNT_EXTERNAL_USER_SHARED_COMPROMISED"
    AFFILIATE_COMPANY_NAME = "AFFILIATE_COMPANY_NAME"
    AFFILIATE_DESCRIPTION_ABSTRACT = "AFFILIATE_DESCRIPTION_ABSTRACT"
    AFFILIATE_DESCRIPTION_CATEGORY = "AFFILIATE_DESCRIPTION_CATEGORY"
    AFFILIATE_DOMAIN_NAME = "AFFILIATE_DOMAIN_NAME"
    AFFILIATE_DOMAIN_UNREGISTERED = "AFFILIATE_DOMAIN_UNREGISTERED"
    AFFILIATE_DOMAIN_WHOIS = "AFFILIATE_DOMAIN_WHOIS"
    AFFILIATE_EMAILADDR = "AFFILIATE_EMAILADDR"
    AFFILIATE_INTERNET_NAME = "AFFILIATE_INTERNET_NAME"
    AFFILIATE_INTERNET_NAME_HIJACKABLE = "AFFILIATE_INTERNET_NAME_HIJACKABLE"
    AFFILIATE_INTERNET_NAME_UNRESOLVED = "AFFILIATE_INTERNET_NAME_UNRESOLVED"
    AFFILIATE_IPADDR = "AFFILIATE_IPADDR"
    AFFILIATE_IPV6_ADDRESS = "AFFILIATE_IPV6_ADDRESS"
    AFFILIATE_WEB_CONTENT = "AFFILIATE_WEB_CONTENT"
    APPSTORE_ENTRY = "APPSTORE_ENTRY"
    BASE64_DATA = "BASE64_DATA"
    BGP_AS_MEMBER = "BGP_AS_MEMBER"
    BGP_AS_OWNER = "BGP_AS_OWNER"
    BITCOIN_ADDRESS = "BITCOIN_ADDRESS"
    BITCOIN_BALANCE = "BITCOIN_BALANCE"
    BLACKLISTED_AFFILIATE_INTERNET_NAME = "BLACKLISTED_AFFILIATE_INTERNET_NAME"
    BLACKLISTED_AFFILIATE_IPADDR = "BLACKLISTED_AFFILIATE_IPADDR"
    BLACKLISTED_COHOST = "BLACKLISTED_COHOST"
    BLACKLISTED_INTERNET_NAME = "BLACKLISTED_INTERNET_NAME"
    BLACKLISTED_IPADDR = "BLACKLISTED_IPADDR"
    BLACKLISTED_NETBLOCK = "BLACKLISTED_NETBLOCK"
    BLACKLISTED_SUBNET = "BLACKLISTED_SUBNET"
    CLOUD_STORAGE_BUCKET = "CLOUD_STORAGE_BUCKET"
    CLOUD_STORAGE_BUCKET_OPEN = "CLOUD_STORAGE_BUCKET_OPEN"
    COMPANY_NAME = "COMPANY_NAME"
    COUNTRY_NAME = "COUNTRY_NAME"
    CO_HOSTED_SITE = "CO_HOSTED_SITE"
    CO_HOSTED_SITE_DOMAIN = "CO_HOSTED_SITE_DOMAIN"
    CO_HOSTED_SITE_DOMAIN_WHOIS = "CO_HOSTED_SITE_DOMAIN_WHOIS"
    CREDIT_CARD_NUMBER = "CREDIT_CARD_NUMBER"
    DARKNET_MENTION_CONTENT = "DARKNET_MENTION_CONTENT"
    DARKNET_MENTION_URL = "DARKNET_MENTION_URL"
    DATE_HUMAN_DOB = "DATE_HUMAN_DOB"
    DEFACED_AFFILIATE_INTERNET_NAME = "DEFACED_AFFILIATE_INTERNET_NAME"
    DEFACED_AFFILIATE_IPADDR = "DEFACED_AFFILIATE_IPADDR"
    DEFACED_COHOST = "DEFACED_COHOST"
    DEFACED_INTERNET_NAME = "DEFACED_INTERNET_NAME"
    DEFACED_IPADDR = "DEFACED_IPADDR"
    DESCRIPTION_ABSTRACT = "DESCRIPTION_ABSTRACT"
    DESCRIPTION_CATEGORY = "DESCRIPTION_CATEGORY"
    DEVICE_TYPE = "DEVICE_TYPE"
    DNS_SPF = "DNS_SPF"
    DNS_SRV = "DNS_SRV"
    DNS_TEXT = "DNS_TEXT"
    DOMAIN_NAME = "DOMAIN_NAME"
    DOMAIN_NAME_PARENT = "DOMAIN_NAME_PARENT"
    DOMAIN_REGISTRAR = "DOMAIN_REGISTRAR"
    DOMAIN_WHOIS = "DOMAIN_WHOIS"
    EMAILADDR = "EMAILADDR"
    EMAILADDR_COMPROMISED = "EMAILADDR_COMPROMISED"
    EMAILADDR_DELIVERABLE = "EMAILADDR_DELIVERABLE"
    EMAILADDR_DISPOSABLE = "EMAILADDR_DISPOSABLE"
    EMAILADDR_GENERIC = "EMAILADDR_GENERIC"
    EMAILADDR_UNDELIVERABLE = "EMAILADDR_UNDELIVERABLE"
    ERROR_MESSAGE = "ERROR_MESSAGE"
    ETHEREUM_ADDRESS = "ETHEREUM_ADDRESS"
    ETHEREUM_BALANCE = "ETHEREUM_BALANCE"
    GEOINFO = "GEOINFO"
    HASH = "HASH"
    HASH_COMPROMISED = "HASH_COMPROMISED"
    HTTP_CODE = "HTTP_CODE"
    HUMAN_NAME = "HUMAN_NAME"
    IBAN_NUMBER = "IBAN_NUMBER"
    INTERESTING_FILE = "INTERESTING_FILE"
    INTERESTING_FILE_HISTORIC = "INTERESTING_FILE_HISTORIC"
    INTERNAL_IP_ADDRESS = "INTERNAL_IP_ADDRESS"
    INTERNET_NAME = "INTERNET_NAME"
    INTERNET_NAME_UNRESOLVED = "INTERNET_NAME_UNRESOLVED"
    IPV6_ADDRESS = "IPV6_ADDRESS"
    IP_ADDRESS = "IP_ADDRESS"
    JOB_TITLE = "JOB_TITLE"
    JUNK_FILE = "JUNK_FILE"
    LEAKSITE_CONTENT = "LEAKSITE_CONTENT"
    LEAKSITE_URL = "LEAKSITE_URL"
    LEI = "LEI"
    LINKED_URL_EXTERNAL = "LINKED_URL_EXTERNAL"
    LINKED_URL_INTERNAL = "LINKED_URL_INTERNAL"
    MALICIOUS_AFFILIATE_INTERNET_NAME = "MALICIOUS_AFFILIATE_INTERNET_NAME"
    MALICIOUS_AFFILIATE_IPADDR = "MALICIOUS_AFFILIATE_IPADDR"
    MALICIOUS_ASN = "MALICIOUS_ASN"
    MALICIOUS_BITCOIN_ADDRESS = "MALICIOUS_BITCOIN_ADDRESS"
    MALICIOUS_COHOST = "MALICIOUS_COHOST"
    MALICIOUS_EMAILADDR = "MALICIOUS_EMAILADDR"
    MALICIOUS_INTERNET_NAME = "MALICIOUS_INTERNET_NAME"
    MALICIOUS_IPADDR = "MALICIOUS_IPADDR"
    MALICIOUS_NETBLOCK = "MALICIOUS_NETBLOCK"
    MALICIOUS_PHONE_NUMBER = "MALICIOUS_PHONE_NUMBER"
    MALICIOUS_SUBNET = "MALICIOUS_SUBNET"
    NETBLOCKV6_MEMBER = "NETBLOCKV6_MEMBER"
    NETBLOCKV6_OWNER = "NETBLOCKV6_OWNER"
    NETBLOCK_MEMBER = "NETBLOCK_MEMBER"
    NETBLOCK_OWNER = "NETBLOCK_OWNER"
    NETBLOCK_WHOIS = "NETBLOCK_WHOIS"
    OPERATING_SYSTEM = "OPERATING_SYSTEM"
    PASSWORD_COMPROMISED = "PASSWORD_COMPROMISED"
    PGP_KEY = "PGP_KEY"
    PHONE_NUMBER = "PHONE_NUMBER"
    PHONE_NUMBER_COMPROMISED = "PHONE_NUMBER_COMPROMISED"
    PHONE_NUMBER_TYPE = "PHONE_NUMBER_TYPE"
    PHYSICAL_ADDRESS = "PHYSICAL_ADDRESS"
    PHYSICAL_COORDINATES = "PHYSICAL_COORDINATES"
    PROVIDER_DNS = "PROVIDER_DNS"
    PROVIDER_HOSTING = "PROVIDER_HOSTING"
    PROVIDER_JAVASCRIPT = "PROVIDER_JAVASCRIPT"
    PROVIDER_MAIL = "PROVIDER_MAIL"
    PROVIDER_TELCO = "PROVIDER_TELCO"
    PROXY_HOST = "PROXY_HOST"
    PUBLIC_CODE_REPO = "PUBLIC_CODE_REPO"
    RAW_DNS_RECORDS = "RAW_DNS_RECORDS"
    RAW_FILE_META_DATA = "RAW_FILE_META_DATA"
    RAW_RIR_DATA = "RAW_RIR_DATA"
    SEARCH_ENGINE_WEB_CONTENT = "SEARCH_ENGINE_WEB_CONTENT"
    SIMILARDOMAIN = "SIMILARDOMAIN"
    SIMILARDOMAIN_WHOIS = "SIMILARDOMAIN_WHOIS"
    SIMILAR_ACCOUNT_EXTERNAL = "SIMILAR_ACCOUNT_EXTERNAL"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    SOFTWARE_USED = "SOFTWARE_USED"
    SSL_CERTIFICATE_EXPIRED = "SSL_CERTIFICATE_EXPIRED"
    SSL_CERTIFICATE_EXPIRING = "SSL_CERTIFICATE_EXPIRING"
    SSL_CERTIFICATE_ISSUED = "SSL_CERTIFICATE_ISSUED"
    SSL_CERTIFICATE_ISSUER = "SSL_CERTIFICATE_ISSUER"
    SSL_CERTIFICATE_MISMATCH = "SSL_CERTIFICATE_MISMATCH"
    SSL_CERTIFICATE_RAW = "SSL_CERTIFICATE_RAW"
    TARGET_WEB_CONTENT = "TARGET_WEB_CONTENT"
    TARGET_WEB_CONTENT_TYPE = "TARGET_WEB_CONTENT_TYPE"
    TARGET_WEB_COOKIE = "TARGET_WEB_COOKIE"
    TCP_PORT_OPEN = "TCP_PORT_OPEN"
    TCP_PORT_OPEN_BANNER = "TCP_PORT_OPEN_BANNER"
    TOR_EXIT_NODE = "TOR_EXIT_NODE"
    UDP_PORT_OPEN = "UDP_PORT_OPEN"
    UDP_PORT_OPEN_INFO = "UDP_PORT_OPEN_INFO"
    URL_ADBLOCKED_EXTERNAL = "URL_ADBLOCKED_EXTERNAL"
    URL_ADBLOCKED_INTERNAL = "URL_ADBLOCKED_INTERNAL"
    URL_FLASH = "URL_FLASH"
    URL_FLASH_HISTORIC = "URL_FLASH_HISTORIC"
    URL_FORM = "URL_FORM"
    URL_FORM_HISTORIC = "URL_FORM_HISTORIC"
    URL_JAVASCRIPT = "URL_JAVASCRIPT"
    URL_JAVASCRIPT_HISTORIC = "URL_JAVASCRIPT_HISTORIC"
    URL_JAVA_APPLET = "URL_JAVA_APPLET"
    URL_JAVA_APPLET_HISTORIC = "URL_JAVA_APPLET_HISTORIC"
    URL_PASSWORD = "URL_PASSWORD"
    URL_PASSWORD_HISTORIC = "URL_PASSWORD_HISTORIC"
    URL_STATIC = "URL_STATIC"
    URL_STATIC_HISTORIC = "URL_STATIC_HISTORIC"
    URL_UPLOAD = "URL_UPLOAD"
    URL_UPLOAD_HISTORIC = "URL_UPLOAD_HISTORIC"
    URL_WEB_FRAMEWORK = "URL_WEB_FRAMEWORK"
    URL_WEB_FRAMEWORK_HISTORIC = "URL_WEB_FRAMEWORK_HISTORIC"
    USERNAME = "USERNAME"
    VPN_HOST = "VPN_HOST"
    VULNERABILITY_CVE_CRITICAL = "VULNERABILITY_CVE_CRITICAL"
    VULNERABILITY_CVE_HIGH = "VULNERABILITY_CVE_HIGH"
    VULNERABILITY_CVE_LOW = "VULNERABILITY_CVE_LOW"
    VULNERABILITY_CVE_MEDIUM = "VULNERABILITY_CVE_MEDIUM"
    VULNERABILITY_DISCLOSURE = "VULNERABILITY_DISCLOSURE"
    VULNERABILITY_GENERAL = "VULNERABILITY_GENERAL"
    WEBSERVER_BANNER = "WEBSERVER_BANNER"
    WEBSERVER_HTTPHEADERS = "WEBSERVER_HTTPHEADERS"
    WEBSERVER_STRANGEHEADER = "WEBSERVER_STRANGEHEADER"
    WEBSERVER_TECHNOLOGY = "WEBSERVER_TECHNOLOGY"
    WEB_ANALYTICS_ID = "WEB_ANALYTICS_ID"
    WIFI_ACCESS_POINT = "WIFI_ACCESS_POINT"
    WIKIPEDIA_PAGE_EDIT = "WIKIPEDIA_PAGE_EDIT"


EVENT_TYPES: dict[EventType, EventTypeDef] = {
    EventType.ROOT: EventTypeDef("ROOT", "Internal SpiderFoot Root event", EventTypeCategory.INTERNAL, is_raw=True),
    EventType.ACCOUNT_EXTERNAL_OWNED: EventTypeDef("ACCOUNT_EXTERNAL_OWNED", "Account on External Site", EventTypeCategory.ENTITY, is_raw=False),
    EventType.ACCOUNT_EXTERNAL_OWNED_COMPROMISED: EventTypeDef("ACCOUNT_EXTERNAL_OWNED_COMPROMISED", "Hacked Account on External Site", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.ACCOUNT_EXTERNAL_USER_SHARED_COMPROMISED: EventTypeDef("ACCOUNT_EXTERNAL_USER_SHARED_COMPROMISED", "Hacked User Account on External Site", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.AFFILIATE_COMPANY_NAME: EventTypeDef("AFFILIATE_COMPANY_NAME", "Affiliate - Company Name", EventTypeCategory.ENTITY, is_raw=False),
    EventType.AFFILIATE_DESCRIPTION_ABSTRACT: EventTypeDef("AFFILIATE_DESCRIPTION_ABSTRACT", "Affiliate Description - Abstract", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.AFFILIATE_DESCRIPTION_CATEGORY: EventTypeDef("AFFILIATE_DESCRIPTION_CATEGORY", "Affiliate Description - Category", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.AFFILIATE_DOMAIN_NAME: EventTypeDef("AFFILIATE_DOMAIN_NAME", "Affiliate - Domain Name", EventTypeCategory.ENTITY, is_raw=False),
    EventType.AFFILIATE_DOMAIN_UNREGISTERED: EventTypeDef("AFFILIATE_DOMAIN_UNREGISTERED", "Affiliate - Domain Name Unregistered", EventTypeCategory.ENTITY, is_raw=False),
    EventType.AFFILIATE_DOMAIN_WHOIS: EventTypeDef("AFFILIATE_DOMAIN_WHOIS", "Affiliate - Domain Whois", EventTypeCategory.DATA, is_raw=True),
    EventType.AFFILIATE_EMAILADDR: EventTypeDef("AFFILIATE_EMAILADDR", "Affiliate - Email Address", EventTypeCategory.ENTITY, is_raw=False),
    EventType.AFFILIATE_INTERNET_NAME: EventTypeDef("AFFILIATE_INTERNET_NAME", "Affiliate - Internet Name", EventTypeCategory.ENTITY, is_raw=False),
    EventType.AFFILIATE_INTERNET_NAME_HIJACKABLE: EventTypeDef("AFFILIATE_INTERNET_NAME_HIJACKABLE", "Affiliate - Internet Name Hijackable", EventTypeCategory.ENTITY, is_raw=False),
    EventType.AFFILIATE_INTERNET_NAME_UNRESOLVED: EventTypeDef("AFFILIATE_INTERNET_NAME_UNRESOLVED", "Affiliate - Internet Name - Unresolved", EventTypeCategory.ENTITY, is_raw=False),
    EventType.AFFILIATE_IPADDR: EventTypeDef("AFFILIATE_IPADDR", "Affiliate - IP Address", EventTypeCategory.ENTITY, is_raw=False),
    EventType.AFFILIATE_IPV6_ADDRESS: EventTypeDef("AFFILIATE_IPV6_ADDRESS", "Affiliate - IPv6 Address", EventTypeCategory.ENTITY, is_raw=False),
    EventType.AFFILIATE_WEB_CONTENT: EventTypeDef("AFFILIATE_WEB_CONTENT", "Affiliate - Web Content", EventTypeCategory.DATA, is_raw=True),
    EventType.APPSTORE_ENTRY: EventTypeDef("APPSTORE_ENTRY", "App Store Entry", EventTypeCategory.ENTITY, is_raw=False),
    EventType.BASE64_DATA: EventTypeDef("BASE64_DATA", "Base64-encoded Data", EventTypeCategory.DATA, is_raw=True),
    EventType.BGP_AS_MEMBER: EventTypeDef("BGP_AS_MEMBER", "BGP AS Membership", EventTypeCategory.ENTITY, is_raw=False),
    EventType.BGP_AS_OWNER: EventTypeDef("BGP_AS_OWNER", "BGP AS Ownership", EventTypeCategory.ENTITY, is_raw=False),
    EventType.BITCOIN_ADDRESS: EventTypeDef("BITCOIN_ADDRESS", "Bitcoin Address", EventTypeCategory.ENTITY, is_raw=False),
    EventType.BITCOIN_BALANCE: EventTypeDef("BITCOIN_BALANCE", "Bitcoin Balance", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.BLACKLISTED_AFFILIATE_INTERNET_NAME: EventTypeDef("BLACKLISTED_AFFILIATE_INTERNET_NAME", "Blacklisted Affiliate Internet Name", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.BLACKLISTED_AFFILIATE_IPADDR: EventTypeDef("BLACKLISTED_AFFILIATE_IPADDR", "Blacklisted Affiliate IP Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.BLACKLISTED_COHOST: EventTypeDef("BLACKLISTED_COHOST", "Blacklisted Co-Hosted Site", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.BLACKLISTED_INTERNET_NAME: EventTypeDef("BLACKLISTED_INTERNET_NAME", "Blacklisted Internet Name", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.BLACKLISTED_IPADDR: EventTypeDef("BLACKLISTED_IPADDR", "Blacklisted IP Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.BLACKLISTED_NETBLOCK: EventTypeDef("BLACKLISTED_NETBLOCK", "Blacklisted IP on Owned Netblock", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.BLACKLISTED_SUBNET: EventTypeDef("BLACKLISTED_SUBNET", "Blacklisted IP on Same Subnet", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.CLOUD_STORAGE_BUCKET: EventTypeDef("CLOUD_STORAGE_BUCKET", "Cloud Storage Bucket", EventTypeCategory.ENTITY, is_raw=False),
    EventType.CLOUD_STORAGE_BUCKET_OPEN: EventTypeDef("CLOUD_STORAGE_BUCKET_OPEN", "Cloud Storage Bucket Open", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.COMPANY_NAME: EventTypeDef("COMPANY_NAME", "Company Name", EventTypeCategory.ENTITY, is_raw=False),
    EventType.COUNTRY_NAME: EventTypeDef("COUNTRY_NAME", "Country Name", EventTypeCategory.ENTITY, is_raw=False),
    EventType.CO_HOSTED_SITE: EventTypeDef("CO_HOSTED_SITE", "Co-Hosted Site", EventTypeCategory.ENTITY, is_raw=False),
    EventType.CO_HOSTED_SITE_DOMAIN: EventTypeDef("CO_HOSTED_SITE_DOMAIN", "Co-Hosted Site - Domain Name", EventTypeCategory.ENTITY, is_raw=False),
    EventType.CO_HOSTED_SITE_DOMAIN_WHOIS: EventTypeDef("CO_HOSTED_SITE_DOMAIN_WHOIS", "Co-Hosted Site - Domain Whois", EventTypeCategory.DATA, is_raw=True),
    EventType.CREDIT_CARD_NUMBER: EventTypeDef("CREDIT_CARD_NUMBER", "Credit Card Number", EventTypeCategory.ENTITY, is_raw=False),
    EventType.DARKNET_MENTION_CONTENT: EventTypeDef("DARKNET_MENTION_CONTENT", "Darknet Mention Web Content", EventTypeCategory.DATA, is_raw=True),
    EventType.DARKNET_MENTION_URL: EventTypeDef("DARKNET_MENTION_URL", "Darknet Mention URL", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.DATE_HUMAN_DOB: EventTypeDef("DATE_HUMAN_DOB", "Date of Birth", EventTypeCategory.ENTITY, is_raw=False),
    EventType.DEFACED_AFFILIATE_INTERNET_NAME: EventTypeDef("DEFACED_AFFILIATE_INTERNET_NAME", "Defaced Affiliate", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.DEFACED_AFFILIATE_IPADDR: EventTypeDef("DEFACED_AFFILIATE_IPADDR", "Defaced Affiliate IP Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.DEFACED_COHOST: EventTypeDef("DEFACED_COHOST", "Defaced Co-Hosted Site", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.DEFACED_INTERNET_NAME: EventTypeDef("DEFACED_INTERNET_NAME", "Defaced", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.DEFACED_IPADDR: EventTypeDef("DEFACED_IPADDR", "Defaced IP Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.DESCRIPTION_ABSTRACT: EventTypeDef("DESCRIPTION_ABSTRACT", "Description - Abstract", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.DESCRIPTION_CATEGORY: EventTypeDef("DESCRIPTION_CATEGORY", "Description - Category", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.DEVICE_TYPE: EventTypeDef("DEVICE_TYPE", "Device Type", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.DNS_SPF: EventTypeDef("DNS_SPF", "DNS SPF Record", EventTypeCategory.DATA, is_raw=False),
    EventType.DNS_SRV: EventTypeDef("DNS_SRV", "DNS SRV Record", EventTypeCategory.DATA, is_raw=False),
    EventType.DNS_TEXT: EventTypeDef("DNS_TEXT", "DNS TXT Record", EventTypeCategory.DATA, is_raw=False),
    EventType.DOMAIN_NAME: EventTypeDef("DOMAIN_NAME", "Domain Name", EventTypeCategory.ENTITY, is_raw=False),
    EventType.DOMAIN_NAME_PARENT: EventTypeDef("DOMAIN_NAME_PARENT", "Domain Name (Parent)", EventTypeCategory.ENTITY, is_raw=False),
    EventType.DOMAIN_REGISTRAR: EventTypeDef("DOMAIN_REGISTRAR", "Domain Registrar", EventTypeCategory.ENTITY, is_raw=False),
    EventType.DOMAIN_WHOIS: EventTypeDef("DOMAIN_WHOIS", "Domain Whois", EventTypeCategory.DATA, is_raw=True),
    EventType.EMAILADDR: EventTypeDef("EMAILADDR", "Email Address", EventTypeCategory.ENTITY, is_raw=False),
    EventType.EMAILADDR_COMPROMISED: EventTypeDef("EMAILADDR_COMPROMISED", "Hacked Email Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.EMAILADDR_DELIVERABLE: EventTypeDef("EMAILADDR_DELIVERABLE", "Deliverable Email Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.EMAILADDR_DISPOSABLE: EventTypeDef("EMAILADDR_DISPOSABLE", "Disposable Email Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.EMAILADDR_GENERIC: EventTypeDef("EMAILADDR_GENERIC", "Email Address - Generic", EventTypeCategory.ENTITY, is_raw=False),
    EventType.EMAILADDR_UNDELIVERABLE: EventTypeDef("EMAILADDR_UNDELIVERABLE", "Undeliverable Email Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.ERROR_MESSAGE: EventTypeDef("ERROR_MESSAGE", "Error Message", EventTypeCategory.DATA, is_raw=False),
    EventType.ETHEREUM_ADDRESS: EventTypeDef("ETHEREUM_ADDRESS", "Ethereum Address", EventTypeCategory.ENTITY, is_raw=False),
    EventType.ETHEREUM_BALANCE: EventTypeDef("ETHEREUM_BALANCE", "Ethereum Balance", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.GEOINFO: EventTypeDef("GEOINFO", "Physical Location", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.HASH: EventTypeDef("HASH", "Hash", EventTypeCategory.DATA, is_raw=False),
    EventType.HASH_COMPROMISED: EventTypeDef("HASH_COMPROMISED", "Compromised Password Hash", EventTypeCategory.DATA, is_raw=False),
    EventType.HTTP_CODE: EventTypeDef("HTTP_CODE", "HTTP Status Code", EventTypeCategory.DATA, is_raw=False),
    EventType.HUMAN_NAME: EventTypeDef("HUMAN_NAME", "Human Name", EventTypeCategory.ENTITY, is_raw=False),
    EventType.IBAN_NUMBER: EventTypeDef("IBAN_NUMBER", "IBAN Number", EventTypeCategory.ENTITY, is_raw=False),
    EventType.INTERESTING_FILE: EventTypeDef("INTERESTING_FILE", "Interesting File", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.INTERESTING_FILE_HISTORIC: EventTypeDef("INTERESTING_FILE_HISTORIC", "Historic Interesting File", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.INTERNAL_IP_ADDRESS: EventTypeDef("INTERNAL_IP_ADDRESS", "IP Address - Internal Network", EventTypeCategory.ENTITY, is_raw=False),
    EventType.INTERNET_NAME: EventTypeDef("INTERNET_NAME", "Internet Name", EventTypeCategory.ENTITY, is_raw=False),
    EventType.INTERNET_NAME_UNRESOLVED: EventTypeDef("INTERNET_NAME_UNRESOLVED", "Internet Name - Unresolved", EventTypeCategory.ENTITY, is_raw=False),
    EventType.IPV6_ADDRESS: EventTypeDef("IPV6_ADDRESS", "IPv6 Address", EventTypeCategory.ENTITY, is_raw=False),
    EventType.IP_ADDRESS: EventTypeDef("IP_ADDRESS", "IP Address", EventTypeCategory.ENTITY, is_raw=False),
    EventType.JOB_TITLE: EventTypeDef("JOB_TITLE", "Job Title", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.JUNK_FILE: EventTypeDef("JUNK_FILE", "Junk File", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.LEAKSITE_CONTENT: EventTypeDef("LEAKSITE_CONTENT", "Leak Site Content", EventTypeCategory.DATA, is_raw=True),
    EventType.LEAKSITE_URL: EventTypeDef("LEAKSITE_URL", "Leak Site URL", EventTypeCategory.ENTITY, is_raw=False),
    EventType.LEI: EventTypeDef("LEI", "Legal Entity Identifier", EventTypeCategory.ENTITY, is_raw=False),
    EventType.LINKED_URL_EXTERNAL: EventTypeDef("LINKED_URL_EXTERNAL", "Linked URL - External", EventTypeCategory.SUBENTITY, is_raw=False),
    EventType.LINKED_URL_INTERNAL: EventTypeDef("LINKED_URL_INTERNAL", "Linked URL - Internal", EventTypeCategory.SUBENTITY, is_raw=False),
    EventType.MALICIOUS_AFFILIATE_INTERNET_NAME: EventTypeDef("MALICIOUS_AFFILIATE_INTERNET_NAME", "Malicious Affiliate", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_AFFILIATE_IPADDR: EventTypeDef("MALICIOUS_AFFILIATE_IPADDR", "Malicious Affiliate IP Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_ASN: EventTypeDef("MALICIOUS_ASN", "Malicious AS", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_BITCOIN_ADDRESS: EventTypeDef("MALICIOUS_BITCOIN_ADDRESS", "Malicious Bitcoin Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_COHOST: EventTypeDef("MALICIOUS_COHOST", "Malicious Co-Hosted Site", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_EMAILADDR: EventTypeDef("MALICIOUS_EMAILADDR", "Malicious E-mail Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_INTERNET_NAME: EventTypeDef("MALICIOUS_INTERNET_NAME", "Malicious Internet Name", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_IPADDR: EventTypeDef("MALICIOUS_IPADDR", "Malicious IP Address", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_NETBLOCK: EventTypeDef("MALICIOUS_NETBLOCK", "Malicious IP on Owned Netblock", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_PHONE_NUMBER: EventTypeDef("MALICIOUS_PHONE_NUMBER", "Malicious Phone Number", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.MALICIOUS_SUBNET: EventTypeDef("MALICIOUS_SUBNET", "Malicious IP on Same Subnet", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.NETBLOCKV6_MEMBER: EventTypeDef("NETBLOCKV6_MEMBER", "Netblock IPv6 Membership", EventTypeCategory.ENTITY, is_raw=False),
    EventType.NETBLOCKV6_OWNER: EventTypeDef("NETBLOCKV6_OWNER", "Netblock IPv6 Ownership", EventTypeCategory.ENTITY, is_raw=False),
    EventType.NETBLOCK_MEMBER: EventTypeDef("NETBLOCK_MEMBER", "Netblock Membership", EventTypeCategory.ENTITY, is_raw=False),
    EventType.NETBLOCK_OWNER: EventTypeDef("NETBLOCK_OWNER", "Netblock Ownership", EventTypeCategory.ENTITY, is_raw=False),
    EventType.NETBLOCK_WHOIS: EventTypeDef("NETBLOCK_WHOIS", "Netblock Whois", EventTypeCategory.DATA, is_raw=True),
    EventType.OPERATING_SYSTEM: EventTypeDef("OPERATING_SYSTEM", "Operating System", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.PASSWORD_COMPROMISED: EventTypeDef("PASSWORD_COMPROMISED", "Compromised Password", EventTypeCategory.DATA, is_raw=False),
    EventType.PGP_KEY: EventTypeDef("PGP_KEY", "PGP Public Key", EventTypeCategory.DATA, is_raw=False),
    EventType.PHONE_NUMBER: EventTypeDef("PHONE_NUMBER", "Phone Number", EventTypeCategory.ENTITY, is_raw=False),
    EventType.PHONE_NUMBER_COMPROMISED: EventTypeDef("PHONE_NUMBER_COMPROMISED", "Phone Number Compromised", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.PHONE_NUMBER_TYPE: EventTypeDef("PHONE_NUMBER_TYPE", "Phone Number Type", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.PHYSICAL_ADDRESS: EventTypeDef("PHYSICAL_ADDRESS", "Physical Address", EventTypeCategory.ENTITY, is_raw=False),
    EventType.PHYSICAL_COORDINATES: EventTypeDef("PHYSICAL_COORDINATES", "Physical Coordinates", EventTypeCategory.ENTITY, is_raw=False),
    EventType.PROVIDER_DNS: EventTypeDef("PROVIDER_DNS", "Name Server (DNS NS Records)", EventTypeCategory.ENTITY, is_raw=False),
    EventType.PROVIDER_HOSTING: EventTypeDef("PROVIDER_HOSTING", "Hosting Provider", EventTypeCategory.ENTITY, is_raw=False),
    EventType.PROVIDER_JAVASCRIPT: EventTypeDef("PROVIDER_JAVASCRIPT", "Externally Hosted Javascript", EventTypeCategory.ENTITY, is_raw=False),
    EventType.PROVIDER_MAIL: EventTypeDef("PROVIDER_MAIL", "Email Gateway (DNS MX Records)", EventTypeCategory.ENTITY, is_raw=False),
    EventType.PROVIDER_TELCO: EventTypeDef("PROVIDER_TELCO", "Telecommunications Provider", EventTypeCategory.ENTITY, is_raw=False),
    EventType.PROXY_HOST: EventTypeDef("PROXY_HOST", "Proxy Host", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.PUBLIC_CODE_REPO: EventTypeDef("PUBLIC_CODE_REPO", "Public Code Repository", EventTypeCategory.ENTITY, is_raw=False),
    EventType.RAW_DNS_RECORDS: EventTypeDef("RAW_DNS_RECORDS", "Raw DNS Records", EventTypeCategory.DATA, is_raw=True),
    EventType.RAW_FILE_META_DATA: EventTypeDef("RAW_FILE_META_DATA", "Raw File Meta Data", EventTypeCategory.DATA, is_raw=True),
    EventType.RAW_RIR_DATA: EventTypeDef("RAW_RIR_DATA", "Raw Data from RIRs/APIs", EventTypeCategory.DATA, is_raw=True),
    EventType.SEARCH_ENGINE_WEB_CONTENT: EventTypeDef("SEARCH_ENGINE_WEB_CONTENT", "Search Engine Web Content", EventTypeCategory.DATA, is_raw=True),
    EventType.SIMILARDOMAIN: EventTypeDef("SIMILARDOMAIN", "Similar Domain", EventTypeCategory.ENTITY, is_raw=False),
    EventType.SIMILARDOMAIN_WHOIS: EventTypeDef("SIMILARDOMAIN_WHOIS", "Similar Domain - Whois", EventTypeCategory.DATA, is_raw=True),
    EventType.SIMILAR_ACCOUNT_EXTERNAL: EventTypeDef("SIMILAR_ACCOUNT_EXTERNAL", "Similar Account on External Site", EventTypeCategory.ENTITY, is_raw=False),
    EventType.SOCIAL_MEDIA: EventTypeDef("SOCIAL_MEDIA", "Social Media Presence", EventTypeCategory.ENTITY, is_raw=False),
    EventType.SOFTWARE_USED: EventTypeDef("SOFTWARE_USED", "Software Used", EventTypeCategory.SUBENTITY, is_raw=False),
    EventType.SSL_CERTIFICATE_EXPIRED: EventTypeDef("SSL_CERTIFICATE_EXPIRED", "SSL Certificate Expired", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.SSL_CERTIFICATE_EXPIRING: EventTypeDef("SSL_CERTIFICATE_EXPIRING", "SSL Certificate Expiring", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.SSL_CERTIFICATE_ISSUED: EventTypeDef("SSL_CERTIFICATE_ISSUED", "SSL Certificate - Issued to", EventTypeCategory.ENTITY, is_raw=False),
    EventType.SSL_CERTIFICATE_ISSUER: EventTypeDef("SSL_CERTIFICATE_ISSUER", "SSL Certificate - Issued by", EventTypeCategory.ENTITY, is_raw=False),
    EventType.SSL_CERTIFICATE_MISMATCH: EventTypeDef("SSL_CERTIFICATE_MISMATCH", "SSL Certificate Host Mismatch", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.SSL_CERTIFICATE_RAW: EventTypeDef("SSL_CERTIFICATE_RAW", "SSL Certificate - Raw Data", EventTypeCategory.DATA, is_raw=True),
    EventType.TARGET_WEB_CONTENT: EventTypeDef("TARGET_WEB_CONTENT", "Web Content", EventTypeCategory.DATA, is_raw=True),
    EventType.TARGET_WEB_CONTENT_TYPE: EventTypeDef("TARGET_WEB_CONTENT_TYPE", "Web Content Type", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.TARGET_WEB_COOKIE: EventTypeDef("TARGET_WEB_COOKIE", "Cookies", EventTypeCategory.DATA, is_raw=False),
    EventType.TCP_PORT_OPEN: EventTypeDef("TCP_PORT_OPEN", "Open TCP Port", EventTypeCategory.SUBENTITY, is_raw=False),
    EventType.TCP_PORT_OPEN_BANNER: EventTypeDef("TCP_PORT_OPEN_BANNER", "Open TCP Port Banner", EventTypeCategory.DATA, is_raw=False),
    EventType.TOR_EXIT_NODE: EventTypeDef("TOR_EXIT_NODE", "TOR Exit Node", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.UDP_PORT_OPEN: EventTypeDef("UDP_PORT_OPEN", "Open UDP Port", EventTypeCategory.SUBENTITY, is_raw=False),
    EventType.UDP_PORT_OPEN_INFO: EventTypeDef("UDP_PORT_OPEN_INFO", "Open UDP Port Information", EventTypeCategory.DATA, is_raw=False),
    EventType.URL_ADBLOCKED_EXTERNAL: EventTypeDef("URL_ADBLOCKED_EXTERNAL", "URL (AdBlocked External)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_ADBLOCKED_INTERNAL: EventTypeDef("URL_ADBLOCKED_INTERNAL", "URL (AdBlocked Internal)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_FLASH: EventTypeDef("URL_FLASH", "URL (Uses Flash)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_FLASH_HISTORIC: EventTypeDef("URL_FLASH_HISTORIC", "Historic URL (Uses Flash)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_FORM: EventTypeDef("URL_FORM", "URL (Form)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_FORM_HISTORIC: EventTypeDef("URL_FORM_HISTORIC", "Historic URL (Form)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_JAVASCRIPT: EventTypeDef("URL_JAVASCRIPT", "URL (Uses Javascript)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_JAVASCRIPT_HISTORIC: EventTypeDef("URL_JAVASCRIPT_HISTORIC", "Historic URL (Uses Javascript)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_JAVA_APPLET: EventTypeDef("URL_JAVA_APPLET", "URL (Uses Java Applet)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_JAVA_APPLET_HISTORIC: EventTypeDef("URL_JAVA_APPLET_HISTORIC", "Historic URL (Uses Java Applet)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_PASSWORD: EventTypeDef("URL_PASSWORD", "URL (Accepts Passwords)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_PASSWORD_HISTORIC: EventTypeDef("URL_PASSWORD_HISTORIC", "Historic URL (Accepts Passwords)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_STATIC: EventTypeDef("URL_STATIC", "URL (Purely Static)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_STATIC_HISTORIC: EventTypeDef("URL_STATIC_HISTORIC", "Historic URL (Purely Static)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_UPLOAD: EventTypeDef("URL_UPLOAD", "URL (Accepts Uploads)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_UPLOAD_HISTORIC: EventTypeDef("URL_UPLOAD_HISTORIC", "Historic URL (Accepts Uploads)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_WEB_FRAMEWORK: EventTypeDef("URL_WEB_FRAMEWORK", "URL (Uses a Web Framework)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.URL_WEB_FRAMEWORK_HISTORIC: EventTypeDef("URL_WEB_FRAMEWORK_HISTORIC", "Historic URL (Uses a Web Framework)", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.USERNAME: EventTypeDef("USERNAME", "Username", EventTypeCategory.ENTITY, is_raw=False),
    EventType.VPN_HOST: EventTypeDef("VPN_HOST", "VPN Host", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.VULNERABILITY_CVE_CRITICAL: EventTypeDef("VULNERABILITY_CVE_CRITICAL", "Vulnerability - CVE Critical", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.VULNERABILITY_CVE_HIGH: EventTypeDef("VULNERABILITY_CVE_HIGH", "Vulnerability - CVE High", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.VULNERABILITY_CVE_LOW: EventTypeDef("VULNERABILITY_CVE_LOW", "Vulnerability - CVE Low", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.VULNERABILITY_CVE_MEDIUM: EventTypeDef("VULNERABILITY_CVE_MEDIUM", "Vulnerability - CVE Medium", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.VULNERABILITY_DISCLOSURE: EventTypeDef("VULNERABILITY_DISCLOSURE", "Vulnerability - Third Party Disclosure", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.VULNERABILITY_GENERAL: EventTypeDef("VULNERABILITY_GENERAL", "Vulnerability - General", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.WEBSERVER_BANNER: EventTypeDef("WEBSERVER_BANNER", "Web Server", EventTypeCategory.DATA, is_raw=False),
    EventType.WEBSERVER_HTTPHEADERS: EventTypeDef("WEBSERVER_HTTPHEADERS", "HTTP Headers", EventTypeCategory.DATA, is_raw=True),
    EventType.WEBSERVER_STRANGEHEADER: EventTypeDef("WEBSERVER_STRANGEHEADER", "Non-Standard HTTP Header", EventTypeCategory.DATA, is_raw=False),
    EventType.WEBSERVER_TECHNOLOGY: EventTypeDef("WEBSERVER_TECHNOLOGY", "Web Technology", EventTypeCategory.DESCRIPTOR, is_raw=False),
    EventType.WEB_ANALYTICS_ID: EventTypeDef("WEB_ANALYTICS_ID", "Web Analytics", EventTypeCategory.ENTITY, is_raw=False),
    EventType.WIFI_ACCESS_POINT: EventTypeDef("WIFI_ACCESS_POINT", "WiFi Access Point Nearby", EventTypeCategory.ENTITY, is_raw=False),
    EventType.WIKIPEDIA_PAGE_EDIT: EventTypeDef("WIKIPEDIA_PAGE_EDIT", "Wikipedia Page Edit", EventTypeCategory.DESCRIPTOR, is_raw=False),
}
