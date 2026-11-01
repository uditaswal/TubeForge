# Example batch plan (3 Shorts)

Import this file on the Studio "Batch plans" page. One `##` heading and one fenced `yaml` block per short.
`beats[].t` is the start second, or a range such as `"0-10"`. `publish_at` is metadata only. Claims in
`claims_to_verify` and URLs in `sources` are for the human reviewer; the pipeline treats the brief as
unverified and still requires source-grounded scripts.

## 2026-11-03 · Short 1 · Storage layer

```yaml
id: sd-001-sql-vs-nosql
title: "Why Amazon Uses DynamoDB for Some Workloads"
concept: "SQL vs NoSQL: scalability and schema flexibility"
length_s: 60
ending: loop
publish_at: 2026-11-03T09:00:00+05:30
hook: "Billions of products load instantly. Is it really one relational database?"
beats:
  - {t: "0-10", point: "Hook: how a product page loads fast at huge scale"}
  - {t: "10-40", point: "Strict relational schemas and transactions get costly at huge read volume; key-value stores trade some guarantees for scale and flexible product metadata"}
  - {t: "40-60", point: "Use a key-value store for high-scale, flexible reads; keep SQL where you need joins and strong consistency"}
cta: "Full deep-dive coming in the long-form video"
claims_to_verify:
  - "Amazon uses DynamoDB for parts of its catalog and still uses relational databases elsewhere"
sources: []
thumbnail: {text: "SQL Dies at Scale?", visual: "SQL logo vs NoSQL logo with a VS badge"}
tags: [system design, sql, nosql, dynamodb]
```

## 2026-11-03 · Short 2 · Caching layer

```yaml
id: sd-002-in-memory-cache
title: "The 1-Millisecond Trick Behind Fast APIs"
concept: "In-memory caching with Redis or Memcached"
length_s: 60
publish_at: 2026-11-03T13:00:00+05:30
beats:
  - {t: "0-10", point: "Hook: how a feed loads in a blink without hammering the database"}
  - {t: "10-40", point: "Disk and network database reads versus RAM reads; a cache hit skips the query entirely"}
  - {t: "40-60", point: "Put a cache in front of read-heavy, rarely-changing data; know when it goes stale"}
thumbnail: {text: "100x Faster APIs?", visual: "speedometer, red database vs green cache"}
tags: [system design, caching, redis]
```

## 2026-11-03 · Short 3 · Traffic layer

```yaml
id: sd-003-load-balancing
title: "What Happens When a Million People Click Buy at Once?"
concept: "Load balancing and reverse proxies"
length_s: 60
publish_at: 2026-11-03T18:00:00+05:30
beats:
  - {t: "0-10", point: "Hook: a flash sale hits at midnight and one server would melt"}
  - {t: "10-40", point: "A load balancer spreads requests across many servers, like a traffic cop opening more toll lanes (round robin, least connections)"}
  - {t: "40-60", point: "It removes the single point of failure and lets you scale horizontally"}
thumbnail: {text: "Stop Server Crashes", visual: "server on fire vs traffic cop icon"}
tags: [system design, load balancing]
```
