# Tier 2 dead-module audit — decisions

**Audit date:** 2026-04-20
**Researched by:** parallel subagent dispatch across 78 `FREE_AUTH_LIMITED` / `FREE_AUTH_UNLIMITED` / `FREE_NOAUTH_LIMITED` modules.
**Reviewer:** user marks up any `keep`/`remove` overrides inline before Task 3 executes.

## Bucket definitions

- **DEAD** — DNS gone, 404, or explicit shut-down notice.
- **ACQUIRED** — absorbed into a paid product; ex-free API unavailable.
- **PAYWALLED** — free tier removed since the module was written.
- **PUNITIVE-FREE** — free tier exists but <100 requests/month (or otherwise unusable for real scans).
- **USABLE-FREE** — free tier works, ≥1000 requests/month (or similar substantive allotment).
- **UNKNOWN** — could not determine with confidence from public pages.

Verdict is `keep` for USABLE-FREE and UNKNOWN (conservative — user overrides for UNKNOWNs if they know more), `remove` for the other four.

## Aggregate

- Total researched: **78**
- Verdict `keep`: **40** (35 USABLE-FREE + 5 UNKNOWN)
- Verdict `remove`: **38** (split across DEAD, ACQUIRED, PAYWALLED, PUNITIVE-FREE)

## Flagged discrepancies for reviewer

Three modules all use the **Google Custom Search JSON API** (100 queries/day free, API closed to new customers, sunset Jan 2027). Two subagents marked them PUNITIVE-FREE; one marked the same API USABLE-FREE. Bringing them for your call:

- `sfp_googlesearch` — PUNITIVE-FREE → remove (current verdict)
- `sfp_pastebin` — PUNITIVE-FREE → remove (current verdict)
- `sfp_socialprofiles` — USABLE-FREE → keep (inconsistent with the other two)

**Recommendation:** align all three to PUNITIVE-FREE → remove, since Google is actively deprecating the API and new users can't get access. Flag `sfp_socialprofiles` for override if you want consistency.

## Decisions

| Module | Service | Bucket | Evidence URL | Verdict | Notes |
|---|---|---|---|---|---|
| sfp_abstractapi | AbstractAPI | USABLE-FREE | https://www.abstractapi.com/api/ip-geolocation-api | keep | Free plan 1,000 req/mo, no card required |
| sfp_abusech | abuse.ch (MalwareBazaar) | USABLE-FREE | https://bazaar.abuse.ch/api/ | keep | Free auth-key API for non-commercial use; fair-use daily limit |
| sfp_abuseipdb | AbuseIPDB | USABLE-FREE | https://www.abuseipdb.com/pricing | keep | Free plan 1,000 checks/day forever |
| sfp_abusix | Abusix Mail Intelligence | USABLE-FREE | https://abusix.com/pricing/ | keep | Free plan 5,000 DNSBL queries/day |
| sfp_adblock | AdBlock Plus / EasyList | USABLE-FREE | https://adblockplus.org/ | keep | Free open-source filter lists, no API/key needed |
| sfp_alienvault | AlienVault OTX (LevelBlue) | UNKNOWN | https://otx.alienvault.com/ | keep | JS-shell page; couldn't confirm free-tier limits from HTML |
| sfp_apple_itunes | Apple iTunes Search | USABLE-FREE | https://itunes.apple.com/ | keep | Public unauthenticated search API (~20 req/min) |
| sfp_binaryedge | BinaryEdge (Coalition) | ACQUIRED | https://help.coalitioninc.com/hc/en-us/articles/34383910057371-BinaryEdge-Transition-FAQ | remove | Domain 301-redirects to Coalition transition FAQ; standalone API/free tier gone |
| sfp_bingsearch | Bing Web Search API | DEAD | https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/overview | remove | Docs marked retired/archived; Bing Search APIs retired by Microsoft (2025) |
| sfp_bingsharedip | Bing Web Search API | DEAD | https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/overview | remove | Same — Bing Search APIs retired |
| sfp_bitcoinabuse | BitcoinAbuse.com | ACQUIRED | https://www.bitcoinabuse.com/ | remove | Merged into Chainabuse; original API replaced, no public free API on Chainabuse |
| sfp_bitcoinwhoswho | Bitcoin Who's Who | PUNITIVE-FREE | https://bitcoinwhoswho.com/api | remove | Free API limited to 1 call/day (~30/mo) |
| sfp_botscout | BotScout | USABLE-FREE | https://botscout.com/getkey.htm | keep | Free API key gives 1,500 queries/day |
| sfp_builtwith | BuiltWith | USABLE-FREE | https://api.builtwith.com/free-api | keep | Free API active, rate-limited 1 req/sec; tech-count data only |
| sfp_censys | Censys | USABLE-FREE | https://censys.com/pricing | keep | Free account includes API access, 500 results/query; no explicit monthly cap |
| sfp_certspotter | SSLMate CertSpotter | USABLE-FREE | https://sslmate.com/ct_search_api/ | keep | Free "Small" plan: 100 single-host queries/hour, 75/min |
| sfp_circllu | CIRCL Passive DNS | USABLE-FREE | https://www.circl.lu/services/passive-dns/ | keep | Free for trusted partners/CSIRTs; contact-based approval, no paid wall |
| sfp_citadel | Leak-Lookup | PUNITIVE-FREE | https://leak-lookup.com/packages/api | remove | Free tier only 10 searches/day with redacted results |
| sfp_clearbit | Clearbit (HubSpot) | ACQUIRED | https://clearbit.com/ | remove | Absorbed into HubSpot; standalone free API discontinued |
| sfp_comodo | Comodo Secure DNS | USABLE-FREE | https://www.comodo.com/secure-dns/ | keep | Free tier, 300k DNS requests/month |
| sfp_dnsdb | Farsight DNSDB (DomainTools) | ACQUIRED | https://www.domaintools.com/products/farsight-dnsdb/ | remove | Acquired by DomainTools; community/free API discontinued |
| sfp_dnsgrep | Rapid7 Open Data (Sonar) | UNKNOWN | https://opendata.rapid7.com/ | keep | Data still offered but policies changed 2022, access now restricted/approval-based |
| sfp_emailcrawlr | EmailCrawlr | DEAD | https://emailcrawlr.com/ | remove | Domain returning 530/522/400 errors; site appears offline |
| sfp_emailrep | EmailRep (Sublime Security) | ACQUIRED | https://docs.sublime.security/reference/emailrep-introduction | remove | Acquired by Sublime Security; now under their docs |
| sfp_focsec | Focsec | PAYWALLED | https://focsec.com/pricing | remove | Only 14-day trial, then paid ($29/mo+); no permanent free tier |
| sfp_fraudguard | FraudGuard.io | PUNITIVE-FREE | https://fraudguard.io/ | remove | Free tier 10 IP lookups/day (~300/month) |
| sfp_fullcontact | FullContact | UNKNOWN | https://www.fullcontact.com/developer-portal/ | keep | No pricing info public; free tier availability unclear |
| sfp_fullhunt | FullHunt | USABLE-FREE | https://fullhunt.io/ | keep | Community/Console tier offers free API access |
| sfp_gleif | GLEIF | USABLE-FREE | https://api.gleif.org/docs | keep | Public API, no auth required, documented production service |
| sfp_googlemaps | Google Maps Platform | USABLE-FREE | https://mapsplatform.google.com/pricing | keep | Essentials tier offers 10K free calls per SKU per month |
| sfp_googlesafebrowsing | Google Safe Browsing v4 | USABLE-FREE | https://developers.google.com/safe-browsing/v4/usage-limits | keep | API is explicitly free; quotas grantable via console |
| sfp_googlesearch | Google Custom Search JSON | PUNITIVE-FREE | https://developers.google.com/custom-search/v1/overview | remove | 100 queries/day free; API closed to new customers (deprecates Jan 2027) |
| sfp_grayhatwarfare | Grayhat Warfare | PAYWALLED | https://grayhatwarfare.com/packages | remove | Free tier provides no API access; API requires paid account |
| sfp_greynoise | GreyNoise | PAYWALLED | https://www.greynoise.io/ | remove | Main enterprise API is paid/demo-only; no free tier for this module |
| sfp_greynoise_community | GreyNoise Community | PUNITIVE-FREE | https://docs.greynoise.io/docs/using-the-greynoise-community-api | remove | Only 50 searches per week, shared with web UI |
| sfp_honeypot | Project Honey Pot Http:BL | USABLE-FREE | https://www.projecthoneypot.org/httpbl_api.php | keep | Free API key with no documented hard monthly cap |
| sfp_hostio | host.io | USABLE-FREE | https://host.io/pricing | keep | 1000 requests/month free tier |
| sfp_hunter | Hunter.io | PUNITIVE-FREE | https://hunter.io/pricing | remove | Only 50 credits/month on free plan |
| sfp_hybrid_analysis | Hybrid Analysis | USABLE-FREE | https://www.hybrid-analysis.com/docs/api/v2 | keep | Free API key still offered as part of the free community service |
| sfp_iknowwhatyoudownload | iknowwhatyoudownload.com | UNKNOWN | https://iknowwhatyoudownload.com/en/api/ | keep | Site active but API pages return 403 bot-block; pricing not verifiable |
| sfp_intelx | Intelligence X | PUNITIVE-FREE | https://intelx.io/product | remove | Free tier limited to 2 selector searches/day (~60/mo) |
| sfp_ipapico | ipapi.co | USABLE-FREE | https://ipapi.co/ | keep | ~30k lookups/month free (1000/day) for testing |
| sfp_ipapicom | ipapi.com | USABLE-FREE | https://ipapi.com/product | keep | 5000 lookups/month on free trial plan |
| sfp_ipinfo | ipinfo.io | USABLE-FREE | https://ipinfo.io/pricing | keep | Free "Lite" tier with unlimited requests (basic attributes) |
| sfp_ipqualityscore | IPQualityScore | USABLE-FREE | https://www.ipqualityscore.com/plans | keep | 1000 lookups/month, 35/day on free plan |
| sfp_ipregistry | ipregistry.co | USABLE-FREE | https://ipregistry.co/pricing | keep | 100,000 free lookups at signup, non-expiring credits |
| sfp_ipstack | ipstack | PUNITIVE-FREE | https://ipstack.com/pricing | remove | Free trial capped at 5,000 total (not monthly) requests |
| sfp_jsonwhoiscom | JsonWHOIS.com | PAYWALLED | https://jsonwhois.com/pricing | remove | Pricing page only lists paid packages, no free tier advertised |
| sfp_koodous | Koodous | UNKNOWN | https://koodous.com/apks/ | keep | Homepage loads but pricing/API availability could not be verified |
| sfp_leakix | LeakIX | USABLE-FREE | https://leakix.net/plans | keep | Free plan: 3000 API requests/month, 1 req/sec |
| sfp_malwarepatrol | MalwarePatrol | PAYWALLED | https://www.malwarepatrol.net/ | remove | Free block list URL 404s; service now commercial/trial-only |
| sfp_metadefender | MetaDefender Cloud | UNKNOWN | https://metadefender.opswat.com/ | keep | Site loads but pricing page 403s; free tier status not verifiable |
| sfp_nameapi | NameAPI | UNKNOWN | https://www.nameapi.org/ | keep | Site active (v11.2.0 Feb 2026), freemium mentioned but quotas not disclosed |
| sfp_networksdb | NetworksDB.io | USABLE-FREE | https://networksdb.io/api/plans | keep | Free tier: 1,000 queries/month |
| sfp_neutrinoapi | NeutrinoAPI | PUNITIVE-FREE | https://www.neutrinoapi.com/plans/ | remove | Free plan ~10-25 requests/day (~300-750/mo) |
| sfp_numverify | numverify | PUNITIVE-FREE | https://numverify.com/ | remove | Free plan: 100 requests/month |
| sfp_onyphe | Onyphe | PAYWALLED | https://www.onyphe.io/pricing | remove | Paid tiers start at €599/mo; no free API tier listed |
| sfp_opencorporates | OpenCorporates | PAYWALLED | https://opencorporates.com/pricing/ | remove | Minimum tier £2,250/year; no commercial free tier |
| sfp_pastebin | Google Custom Search (for Pastebin) | PUNITIVE-FREE | https://developers.google.com/custom-search/v1/overview | remove | 100 queries/day free; API closed to new customers, sunset Jan 2027 |
| sfp_pulsedive | Pulsedive | UNKNOWN | https://pulsedive.com/ | keep | Service operational, Pro at $29/mo; specific free API quota not disclosed |
| sfp_riskiq | RiskIQ | ACQUIRED | https://www.riskiq.com/ | remove | riskiq.com redirects to Microsoft Defender Threat Intelligence |
| sfp_securitytrails | SecurityTrails | UNKNOWN | https://securitytrails.com/corp/api | keep | Pricing pages return 403; free tier status unverifiable |
| sfp_shodan | Shodan | PAYWALLED | https://account.shodan.io/billing | remove | API requires paid Membership ($49 one-time minimum); no free API plan |
| sfp_snov | Snov.io | PUNITIVE-FREE | https://snov.io/pricing | remove | Trial only: 50 credits/mo, vendor says "not meant to help grow sales" |
| sfp_socialprofiles | Google Custom Search JSON API | USABLE-FREE | https://developers.google.com/custom-search/v1/overview | keep | 100 queries/day free (~3000/mo); API closed to new customers, sunset Jan 2027 — **DISCREPANCY: see flagged note above** |
| sfp_spyonweb | SpyOnWeb | DEAD | http://spyonweb.com/ | remove | Homepage and api.spyonweb.com both ECONNREFUSED |
| sfp_stackoverflow | Stack Exchange API | USABLE-FREE | https://api.stackexchange.com/docs/throttle | keep | Stack Exchange API free; 10k daily quota for authenticated apps |
| sfp_textmagic | TextMagic | PAYWALLED | https://www.textmagic.com/ | remove | Only free trial credit; Caller Name / number lookup is paid pay-as-you-go |
| sfp_threatjammer | ThreatJammer | DEAD | https://threatjammer.com | remove | threatjammer.com 301-redirects to squatted gambling domain |
| sfp_trashpanda | Trashpanda / got-hacked.wtf | DEAD | https://got-hacked.wtf | remove | TLS certificate expired; site unreachable |
| sfp_twilio | Twilio Lookup (Caller Name) | PAYWALLED | https://www.twilio.com/en-us/user-authentication-identity/pricing/lookup | remove | Only number formatting/validation free; caller name identity match is paid |
| sfp_viewdns | ViewDNS.info API | PUNITIVE-FREE | https://viewdns.info/api/pricing/ | remove | 250 one-time trial queries only (not recurring); paid from $29/mo |
| sfp_virustotal | VirusTotal Public API | USABLE-FREE | https://docs.virustotal.com/reference/public-vs-premium-api | keep | 500 requests/day, 4/min (~15k/month) on free public API |
| sfp_whatcms | WhatCMS API | PUNITIVE-FREE | https://whatcms.org/API | remove | 500 detections/month free, 1 req/10s — below 1000/mo threshold |
| sfp_wigle | WiGLE | UNKNOWN | https://wigle.net/ | keep | Registered free accounts supported; exact rate limit not published |
| sfp_xforce | IBM X-Force Exchange | UNKNOWN | https://exchange.xforce.ibmcloud.com/ | keep | Site reachable but login-gated; public pages did not expose free/commercial terms |
| sfp_zetalytics | Zetalytics | PUNITIVE-FREE | https://zetalytics.com/ | remove | Free access is restricted playground only; real queries paid |
| sfp_zonefiles | ZoneFiles.io | DEAD | https://zonefiles.io | remove | zonefiles.io ECONNREFUSED; alternate zonefiles.com empty; service appears offline |
