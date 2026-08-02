"""Build the frozen paired-30 synthetic incident corpus.

The compact scenario table is the reviewed source of truth. Generated JSON is
committed so an experiment never depends on executing this builder at run time.
"""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent


SCENARIOS = [
    ("c01", "Image API memory collapse", "Image requests return 503s after a traffic rise.",
     "image-api", "an unbounded decoded-image cache", "A release removed the decoded-image cache size limit.",
     "Cache entries grow with every unique image and are never evicted.", "The image-api container exceeds its memory limit and is OOM-killed.",
     "Repeated restarts leave no ready image-api capacity.", "Image requests return 503.",
     "edge-proxy", "The edge proxy deployed four minutes before the first 503 and reports a small CPU rise.",
     "Proxy bypass tests still fail, and its upstream-reset count begins only after image-api restarts.",
     "Restoring the cache limit stops memory growth and 503s without changing the proxy.", "The thumbnail database has a harmless 9 ms latency increase."),
    ("c02", "Catalog authentication outage", "Catalog reads fail with authentication errors.",
     "catalog-service", "an expired database credential", "The catalog database credential reached its configured expiry time without rotation.",
     "New catalog database connections are rejected as password expired.", "The connection pool drains as existing sessions close.",
     "Catalog queries cannot acquire a usable database connection.", "Catalog reads return authentication failures.",
     "database failover", "A standby database promotion alert fired shortly before the incident.",
     "Both primary and standby reject the same catalog identity while other identities connect normally.",
     "Rotating only the catalog credential restores reads.", "Search indexing lag rises but remains inside its SLO."),
    ("c03", "Checkout retry amplification", "Checkout latency rises while checkout pods remain healthy.",
     "promotion-service", "a retry policy with excessive attempts and no deadline", "A config revision raised cache retry attempts from two to fifteen and removed the overall deadline.",
     "A brief promotion-cache timeout causes fifteen serial retries per request.", "Retrying calls occupy the promotion outbound connection pool.",
     "Promotion spans dominate checkout request duration.", "Checkout p95 rises above eight seconds.",
     "promotion-cache", "A promotion-cache shard rebalance coincides with the first slow request.",
     "The rebalance lasts seventy seconds, but checkout remains slow until retrying requests drain; the old retry policy tolerates an identical replay.",
     "Restoring two attempts and a deadline clears latency while the cache topology is unchanged.", "Order-write latency doubles but stays below forty milliseconds."),
    ("c04", "Media name-resolution failure", "Only media uploads fail to resolve an internal hostname.",
     "media-service", "an invalid per-service DNS resolver override", "A media deployment points resolv.conf at a retired resolver address.",
     "Media pods send internal DNS queries to an address with no listener.", "Hostname lookups time out before the upload client connects.",
     "No requests reach the media storage service.", "Media uploads fail with name-resolution errors.",
     "cluster-dns", "Cluster DNS latency briefly rises during a node scale event.",
     "Other namespaces resolve the hostname normally, and packet capture shows media queries bypass cluster DNS.",
     "Removing the media-only resolver override restores uploads without changing cluster DNS.", "Media CPU rises from 22 to 27 percent."),
    ("c05", "Webhook TLS rejection", "Partners reject outbound webhooks after midnight.",
     "certificate-automation", "a disabled certificate renewal job", "A namespace migration left the webhook certificate renewal job suspended.",
     "The serving certificate passes its not-after timestamp without replacement.", "TLS handshakes present the expired certificate.",
     "Partner clients terminate the connection before HTTP delivery.", "Outbound webhooks are rejected.",
     "partner firewall", "One partner changed firewall rules during the same maintenance window.",
     "Partners with unchanged firewalls fail identically, and TCP connections complete before TLS rejection.",
     "Renewing the certificate restores all partners without firewall changes.", "Webhook queue depth begins rising after the TLS failures."),
    ("c06", "Payments and order history slowdown", "Payment submissions fail while order history becomes slow.",
     "platform-configuration", "two independent faults: a stale payment endpoint and a missing orders index", "One rollout retains a retired payment endpoint while a separate migration drops the orders customer-time index.",
     "Payment calls target the retired address, while order-history queries perform full scans.", "Payment connections fail and orders database CPU saturates independently.",
     "The two downstream operations delay different request branches.", "Payment submission fails and order history exceeds its latency SLO.",
     "service-mesh", "A service-mesh control-plane restart occurs between the two symptom onsets.",
     "Direct requests reproduce each failure; mesh health is normal, and the two symptoms have different start times.",
     "Correcting the endpoint fixes payments; recreating the index separately fixes order history.", "Inventory cache hit rate drops by one percentage point."),
    ("c07", "Profile connection exhaustion", "Profile requests begin timing out after several hours.",
     "profile-service", "a database connection leak on canceled requests", "A release omits connection cleanup when profile requests are canceled.",
     "Each canceled request leaves one database connection checked out.", "The profile connection pool gradually reaches its maximum.",
     "New profile requests wait for a connection until their deadlines expire.", "Profile requests time out.",
     "database", "Database active sessions rise with the incident and suggest server overload.",
     "Database CPU remains low and leaked sessions are idle from profile-service only.",
     "Deploying the cleanup fix returns pool usage to baseline without resizing the database.", "The avatar CDN records a minor cache-miss increase."),
    ("c08", "Identity token rejection", "Freshly issued tokens are rejected as not yet valid by one zone.",
     "identity-nodes-zone-b", "host clock skew caused by failed time synchronization", "A firewall rule blocks time synchronization traffic from identity nodes in zone B.",
     "Zone-B clocks drift eleven minutes ahead of the signing service.", "Tokens minted or validated across zones have inconsistent not-before comparisons.",
     "Zone-B validators reject otherwise valid fresh tokens.", "Users routed to zone B receive token-not-yet-valid errors.",
     "signing-key rotation", "A signing-key rotation completes near the first rejection.",
     "Rejected tokens verify with both old and new public keys, while their timestamps differ from zone-B wall time.",
     "Restoring time synchronization eliminates rejection without changing keys.", "Identity database replica lag reaches 140 ms."),
    ("c09", "Invoice queue stall", "Invoice processing stops although consumers are running.",
     "invoice-consumer", "an unrecoverable message retried without a dead-letter limit", "A malformed invoice event enters a partition whose consumer retries failures indefinitely.",
     "The poison event fails schema decoding on every attempt and is never committed or dead-lettered.", "The partition remains pinned to the same offset.",
     "Later valid invoice events cannot be consumed from that partition.", "Invoice processing appears stalled.",
     "message-broker", "Broker disk utilization crosses a warning threshold at the same time.",
     "Other partitions progress normally and broker publish latency stays healthy; only one offset repeats.",
     "Dead-lettering the malformed event immediately resumes the partition.", "Email delivery has an unrelated provider retry spike."),
    ("c10", "Session cache stampede", "Login latency spikes at the top of every hour.",
     "session-service", "synchronized cache expiry without request coalescing", "All session-policy entries are written with the same hourly absolute expiry and no refresh jitter.",
     "At expiry, concurrent misses trigger duplicate policy database reads.", "The policy database connection pool saturates under the miss burst.",
     "Session validation waits behind database reads.", "Login latency spikes each hour.",
     "scheduled analytics", "An hourly analytics job starts within the same minute.",
     "Disabling analytics does not alter the spike, while cache-miss count jumps exactly at policy expiry.",
     "Adding expiry jitter and request coalescing removes the spike with analytics still enabled.", "Authentication CPU falls slightly during the incident."),
    ("c11", "Worker autoscaling failure", "A work queue grows despite low reported utilization.",
     "worker-autoscaler", "scaling on an averaged CPU metric that excludes queued work", "A configuration change replaces queue-depth scaling with namespace-average CPU.",
     "Idle auxiliary pods dilute average CPU below the scale-out threshold.", "The autoscaler keeps the worker deployment at its minimum replica count.",
     "Incoming work exceeds the fixed worker throughput.", "The work queue grows continuously.",
     "queue-service", "Queue storage latency increases shortly before backlog growth.",
     "Enqueue and dequeue operation latency remain below limits; replaying the load with queue-depth scaling adds workers promptly.",
     "Restoring queue-depth scaling drains the backlog without modifying the queue service.", "Worker memory usage is stable."),
    ("c12", "Artifact upload disk-full errors", "Artifact uploads fail although disk byte usage is below 50 percent.",
     "artifact-store", "inode exhaustion from abandoned zero-byte temporary files", "A cleanup regression leaves one temporary file per multipart retry.",
     "Millions of zero-byte temporary files consume all filesystem inodes.", "New upload parts fail when the store cannot create another file.",
     "Multipart uploads abort before storing artifact bytes.", "Artifact uploads return disk-full errors.",
     "storage capacity", "The storage dashboard shows a recent capacity alert from another volume.",
     "The affected volume has free bytes but zero free inodes; the capacity alert names a different mount.",
     "Deleting abandoned temporary files restores uploads without adding capacity.", "Artifact metadata database latency is 5 ms higher."),
    ("c13", "Report service deadlock", "Report generation hangs under a particular concurrent workload.",
     "report-service", "opposite lock acquisition order in export and cancellation paths", "A refactor makes export acquire report then account locks while cancellation acquires account then report.",
     "Concurrent export and cancellation each hold one lock while waiting for the other.", "All report worker threads eventually block in the two lock waits.",
     "No worker remains available to complete queued reports.", "Report generation hangs.",
     "database locks", "Database lock-wait graphs appear when reports stop.",
     "The waits are application mutexes and database transactions are idle; thread dumps show the inverse lock order.",
     "Enforcing one lock order removes hangs under the same database workload.", "PDF renderer CPU briefly reaches 70 percent."),
    ("c14", "API throttling storm", "A client exceeds its API quota for minutes after a brief rate limit.",
     "api-client", "ignoring Retry-After and retrying immediately", "A client library update replaces server-directed backoff with immediate parallel retries.",
     "The first 429 response triggers many immediate retries for each request.", "Retry traffic consumes the client's quota as soon as it replenishes.",
     "Sustained 429 responses prevent useful requests from completing.", "The client remains throttled.",
     "api-gateway", "A gateway deployment precedes the first 429.",
     "Other clients using Retry-After recover normally, and the gateway enforces the unchanged documented quota.",
     "Restoring Retry-After handling ends the storm without a gateway rollback.", "A regional latency alert clears before throttling begins."),
    ("c15", "Search result disappearance", "Some valid products disappear from search after a gradual flag rollout.",
     "search-service", "a feature flag applying an inverted availability predicate", "A new ranking flag rolls from 5 to 100 percent and negates the in-stock predicate.",
     "Flagged requests filter products whose availability field is true.", "The candidate set loses valid in-stock products before ranking.",
     "Search responses omit those products even though the index contains them.", "Valid products disappear from search.",
     "indexing pipeline", "Index freshness degrades during the rollout.",
     "Direct index queries contain the missing products, and unflagged requests return them from the same index version.",
     "Disabling the flag restores products without reindexing.", "Recommendation click-through changes during a promotion."),
    ("c16", "Consumer failures after schema rollout", "Legacy consumers reject newly published account events.",
     "event-producer", "publishing a required field with an incompatible type", "The account producer changes balance from an integer to an object without a new schema version.",
     "New events encode balance in a representation legacy consumers cannot deserialize.", "Legacy consumers reject and retry each new event.",
     "Their partitions accumulate lag behind the incompatible event.", "Legacy account consumers stop processing.",
     "schema-registry", "The schema registry restarts during the rollout.",
     "Consumers retrieve the schema successfully; validation shows the producer payload violates the registered old type.",
     "Publishing the old representation resumes consumers without changing the registry.", "One consumer host reports elevated network retransmits."),
    ("c17", "Daily settlement runs twice", "Daily settlement executes twice on daylight-saving transition day.",
     "settlement-scheduler", "scheduling by repeated local wall-clock time without a uniqueness guard", "The scheduler evaluates a local 01:30 cron expression during a fall-back transition.",
     "The local 01:30 timestamp occurs twice with different UTC offsets.", "Both occurrences enqueue an identical settlement date.",
     "Workers accept both jobs because no date-level idempotency key exists.", "Daily settlement executes twice.",
     "operator replay", "An operator logs into the scheduler near the second execution.",
     "Audit logs show no replay command, while enqueue records carry the two distinct UTC offsets.",
     "Adding a settlement-date uniqueness key prevents duplication on a clock-transition replay.", "Bank API latency rises after both jobs start."),
    ("c18", "Healthy pods removed from rotation", "Application pods are healthy but receive no production traffic.",
     "load-balancer", "a health check pointed at an authenticated endpoint", "A load-balancer change moves health checks from /healthz to /status, which requires authentication.",
     "Unauthenticated health probes receive 401 from every otherwise healthy pod.", "The load balancer marks all application backends unhealthy.",
     "Requests have no eligible backend target.", "Production traffic receives gateway errors.",
     "application deployment", "An application image deployment finishes just before traffic loss.",
     "Direct authenticated requests to the new pods succeed, and reverting only the health-check path restores backend health.",
     "Pointing probes back to /healthz restores traffic without rolling back the application.", "Database connection count falls because traffic stops."),
    ("c19", "Missing writes on immediate reads", "Users save settings successfully but immediately read old values.",
     "settings-service", "routing read-after-write requests to a lagging replica", "A routing change sends all settings reads to replicas without session consistency.",
     "The primary commits updates while one replica remains several seconds behind.", "Immediate follow-up reads are routed to the lagging replica.",
     "Those reads return the preceding settings version.", "Users observe old values after successful saves.",
     "browser cache", "A frontend cache release occurs near the first stale read.",
     "Responses include no-cache and direct API reads reproduce staleness only when routed to the lagging replica.",
     "Pinning post-write reads to the primary removes staleness without a frontend rollback.", "Settings write latency remains normal."),
    ("c20", "Outbound connection failures", "Many unrelated services lose outbound connectivity from one node pool.",
     "node-pool-egress", "NAT source-port exhaustion caused by disabled connection reuse", "A base-image update disables HTTP keep-alive for services in one node pool.",
     "Each request opens a new outbound connection and leaves ports in TIME_WAIT.", "The shared NAT gateway exhausts available source-port mappings.",
     "New outbound TCP connections from the pool fail intermittently.", "Multiple services lose outbound connectivity.",
     "external provider", "The largest external provider reports a regional incident.",
     "Connections to unrelated providers fail from the same pool but succeed from other pools; NAT allocation is at its limit.",
     "Restoring connection reuse drops NAT allocation and restores all providers.", "Node CPU remains below 40 percent."),
    ("c21", "Node outage from logging", "A node becomes NotReady and evicts several unrelated pods.",
     "log-agent", "recursive collection of its own error log", "A logging rule begins ingesting the agent's own failed-delivery log.",
     "Each delivery error produces another collected record and another delivery error.", "Recursive logs rapidly fill the node filesystem.",
     "Kubelet loses writable disk space and marks the node under disk pressure.", "The node becomes NotReady and pods are evicted.",
     "container runtime", "A container-runtime warning appears shortly before NotReady.",
     "Runtime storage growth is entirely the log-agent file, and runtime health recovers after that file is removed.",
     "Excluding the self-log stops disk growth and restores node readiness.", "One evicted pod had restarted earlier for an unrelated probe failure."),
    ("c22", "Telemetry-induced pauses", "Request latency develops long periodic pauses after adding a metric label.",
     "api-service", "unbounded metric cardinality from a user ID label", "A telemetry change adds raw user_id to a request counter label.",
     "Every active user creates new long-lived metric series in process memory.", "Heap growth causes increasingly frequent full garbage collections.",
     "Application threads pause during full collections.", "Request latency shows long periodic pauses.",
     "database checkpoint", "Database checkpoints occur at a similar interval.",
     "Slow traces spend the pause inside the API process before database calls, and checkpoint duration is unchanged.",
     "Removing the user_id label stabilizes the heap and removes pauses.", "Network packet loss stays below 0.01 percent."),
    ("c23", "Fallback blocked by circuit breaker", "Requests fail even though a healthy fallback service is available.",
     "routing-service", "a circuit breaker shared across primary and fallback destinations", "A configuration migration assigns primary and fallback calls the same breaker key.",
     "Primary failures open the shared circuit breaker.", "Fallback calls consult the same open breaker and are rejected locally.",
     "No request reaches the healthy fallback service.", "Routing requests fail instead of degrading to fallback.",
     "fallback-service", "Fallback CPU rises shortly before request failures.",
     "Fallback health probes and direct calls succeed, while failed traces show local circuit-open errors with no fallback span.",
     "Using separate breaker keys restores fallback without scaling it.", "Primary error rate remains high as expected."),
    ("c24", "Ledger balance regression", "A small set of account balances move backward after failover.",
     "ledger-consumer", "applying out-of-order balance events without sequence validation", "A failover changes delivery order for retried ledger events.",
     "An older balance event arrives after a newer event for the same account.", "The consumer overwrites current state without comparing sequence numbers.",
     "Stored balance regresses to the older event value.", "Users see balances move backward.",
     "ledger database", "A database failover occurs at the first reported regression.",
     "Commit ordering is correct in the database; consumer logs show sequence 411 applied after 412.",
     "Rejecting lower sequence numbers prevents regression during failover replay.", "Notification delivery is delayed during failover."),
    ("c25", "Encrypted record read failures", "New records are readable, but records written yesterday fail decryption.",
     "key-management", "deleting the previous encryption key before retention expiry", "A key-rotation job deletes the old key immediately instead of retaining it for the configured window.",
     "Yesterday's records still reference the deleted key version.", "Readers cannot retrieve key material for those ciphertexts.",
     "Decryption fails before record parsing.", "Older records become unreadable while new records remain healthy.",
     "storage corruption", "A storage checksum alarm fires for one shard.",
     "Affected records span healthy shards and pass ciphertext checksums; all share the deleted key version.",
     "Restoring the previous key version makes old records readable without restoring storage.", "New-key encryption latency is unchanged."),
    ("c26", "Private content leaked through CDN", "Some users receive another user's personalized page.",
     "cdn-configuration", "a cache key that omits the session-dependent locale and account variant", "A CDN rule starts caching personalized HTML by URL path alone.",
     "Responses for different accounts map to the same cache object.", "The first personalized response populates that shared object.",
     "Subsequent users receive the cached first response.", "Users see another account's personalized page.",
     "application session store", "Session-store latency rises during the first report.",
     "Leaked responses carry another account's correct server rendering and an Age header; origin requests remain correctly isolated.",
     "Adding account and locale variation to the cache key stops leakage without changing sessions.", "Static asset cache hit rate also rises."),
    ("c27", "Duplicate cleanup jobs", "Two workers delete the same expired resources concurrently.",
     "cleanup-leader-election", "a lease duration shorter than worst-case renewal pauses", "The leader lease is shortened below observed garbage-collection pauses.",
     "The active leader pauses beyond the lease duration while continuing its current batch afterward.", "A second worker acquires the expired lease and starts the same scheduled batch.",
     "Both workers process overlapping resource IDs.", "Duplicate cleanup operations occur.",
     "scheduler", "The scheduler emits two start notifications.",
     "Both notifications originate from different valid lease holders; only one schedule record exists.",
     "Extending the lease beyond renewal pauses prevents duplicate workers under the same schedule.", "Deletion API latency rises under duplicate load."),
    ("c28", "Large request network hangs", "Small requests succeed, but requests above 1,400 bytes hang across a new tunnel.",
     "network-tunnel", "a path MTU mismatch with blocked fragmentation-needed messages", "A tunnel change adds encapsulation overhead without lowering interface MTU, while ICMP fragmentation-needed is filtered.",
     "Large packets exceed the effective tunnel path MTU.", "Oversized packets are dropped and path-MTU discovery receives no feedback.",
     "TCP retransmits the same large segments until request timeout.", "Large requests hang while small requests succeed.",
     "application serializer", "A serializer release increases typical request size.",
     "The old serializer also hangs when padded above the threshold, while new small payloads succeed.",
     "Lowering tunnel MTU restores large requests without reverting serialization.", "Server CPU is lower during failed requests."),
    ("c29", "Fallback overload cascade", "A minor recommendation outage expands into homepage failures.",
     "homepage-service", "an unbounded synchronous fallback fan-out", "A fallback change queries every catalog shard when recommendations time out.",
     "Each recommendation timeout triggers parallel synchronous calls to all catalog shards.", "Fallback traffic saturates homepage and catalog connection pools.",
     "Homepage requests wait behind the fallback fan-out.", "Homepage requests fail far beyond the recommendation feature.",
     "recommendation-service", "Recommendation pods restart at the incident start.",
     "Disabling recommendations without fallback keeps homepages healthy; replaying the fan-out against healthy recommendations still saturates pools.",
     "Bounding and asynchronously serving fallback restores homepages while recommendations remain degraded.", "Catalog database cache hit rate falls under extra traffic."),
    ("c30", "CPU throttling with low utilization", "A latency-sensitive service reports low average CPU but high tail latency on one node.",
     "node-cgroup", "an overly restrictive CPU quota inherited from a node-pool policy", "A node-pool policy applies a 100m CPU quota to the service despite a 2-core request.",
     "Short request bursts consume the small quota early in each enforcement period.", "The kernel throttles the service until the next quota period.",
     "Requests accumulate during throttled intervals.", "Tail latency rises despite low time-averaged CPU utilization.",
     "noisy neighbor", "A batch pod starts on the same node before latency rises.",
     "The batch pod's removal does not change throttled-time counters; moving the service preserves latency until its quota is corrected.",
     "Correcting the inherited quota removes throttling and tail latency on the same node.", "Memory bandwidth counters remain normal."),
]


ANSWER_CONTRACT = {
    "root_event_ids": ["evidence ID"],
    "causal_paths": [["ordered evidence IDs from one root to symptom"]],
    "supporting_evidence_ids": ["evidence ID"],
    "counterevidence_ids": ["evidence ID that tests or rejects alternatives"],
    "rejected_distractor_ids": ["evidence ID"],
    "confidence": "number between 0 and 1",
    "explanation": "short causal explanation",
}


def evidence(case_id: str, values: tuple[str, ...]) -> tuple[list[dict[str, str | list[str]]], dict[str, str]]:
    (_, _, _, root_component, _, root_change, root_behavior, intermediate,
     downstream, symptom, distractor_component, distractor, refutation,
     recovery, noise) = values
    rows = [
        ("symptom", "metrics", "user-impact", "Service-level observation", symptom, ["service", "impact"]),
        ("alternative", "change-log", distractor_component, "Concurrent change record", distractor, [distractor_component, "change"]),
        ("alternative_signal", "metrics", distractor_component, "Component monitoring signal", f"Monitoring for {distractor_component} changes at the same time, but does not establish propagation to the symptom.", [distractor_component, "metrics"]),
        ("alternative_test", "experiment", distractor_component, "Isolation test result", refutation, [distractor_component, "test"]),
        ("root_change", "configuration", root_component, "Configuration audit record", root_change, [root_component, "configuration"]),
        ("root_behavior", "logs", root_component, "Component log pattern", root_behavior, [root_component, "logs"]),
        ("intermediate", "metrics", root_component, "Resource-state observation", intermediate, [root_component, "metrics"]),
        ("downstream", "traces", root_component, "Request trace segment", downstream, [root_component, "trace"]),
        ("recovery", "experiment", root_component, "Mitigation experiment", recovery, [root_component, "experiment"]),
        ("noise", "metrics", "unrelated-component", "Adjacent system metric", noise, ["adjacent", "metrics"]),
    ]
    if case_id == "c06":
        rows[4] = ("root_change", "configuration", "payment-client", "Payment client configuration", "A rollout retains a retired payment endpoint after the migration window.", ["payment-client", "configuration"])
        rows[5] = ("root_behavior", "configuration", "orders-database", "Orders schema audit", "A separate schema migration drops the customer-time index used by order history.", ["orders-database", "schema"])
        rows[6] = ("intermediate", "traces", "payment-client", "Payment request trace", "Payment calls target the retired endpoint and fail to connect before submission.", ["payment-client", "trace"])
        rows[7] = ("downstream", "traces", "orders-database", "Order-history query trace", "Order-history queries perform full scans and saturate database CPU.", ["orders-database", "trace"])
    suffixes = [f"{value:02d}" for value in range(1, 11)]
    random.Random(20260803 + int(case_id[1:])).shuffle(suffixes)
    ids = {row[0]: f"ev-{case_id}-{suffix}" for row, suffix in zip(rows, suffixes)}
    items = [
        {
            "id": ids[role],
            "source_type": source_type,
            "component": component,
            "timestamp": f"2026-07-15T12:{index:02d}:00Z",
            "summary": summary,
            "content": content,
            "tags": tags,
        }
        for index, (role, source_type, component, summary, content, tags) in enumerate(rows, start=1)
    ]
    items.sort(key=lambda item: item["id"])
    return items, ids


def build() -> tuple[list[dict], dict[str, dict]]:
    cases = []
    gold = {}
    for values in SCENARIOS:
        case_id, title, prompt, root_component, root_fault, *_ = values
        items, ids = evidence(case_id, values)
        cases.append({
            "id": case_id,
            "title": title,
            "difficulty": "adversarial_causal",
            "prompt": prompt + " Identify every material root cause and trace the propagation to the symptom.",
            "source_types": sorted({item["source_type"] for item in items}),
            "answer_contract": ANSWER_CONTRACT,
            "evidence": items,
        })
        roots = [ids["root_change"]]
        if case_id == "c06":
            roots.append(ids["root_behavior"])
        required_paths = [[
            ids["root_change"], ids["root_behavior"], ids["intermediate"],
            ids["downstream"], ids["symptom"],
        ]]
        if case_id == "c06":
            required_paths = [
                [ids["root_change"], ids["intermediate"], ids["symptom"]],
                [ids["root_behavior"], ids["downstream"], ids["symptom"]],
            ]
        gold[case_id] = {
            "root_event_ids": roots,
            "root_label": {"component": root_component, "fault": root_fault},
            "required_paths": required_paths,
            "accepted_causal_event_ids": [
                ids["root_change"], ids["root_behavior"], ids["intermediate"],
                ids["downstream"], ids["symptom"], ids["recovery"],
            ],
            "critical_supporting_evidence_ids": [
                ids["alternative_test"], ids["root_change"], ids["root_behavior"],
                ids["intermediate"], ids["downstream"], ids["recovery"],
            ],
            "accepted_supporting_evidence_ids": [
                ids["symptom"], ids["alternative_test"], ids["root_change"],
                ids["root_behavior"], ids["intermediate"], ids["downstream"],
                ids["recovery"],
            ],
            "falsifying_evidence_ids": [ids["alternative_test"]],
            "distractor_evidence_ids": [
                ids["alternative"], ids["alternative_signal"], ids["noise"],
            ],
        }
    return cases, gold


if __name__ == "__main__":
    public, sealed = build()
    (ROOT / "cases.json").write_text(json.dumps(public, indent=2) + "\n", encoding="utf-8")
    (ROOT / "gold.json").write_text(json.dumps(sealed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
