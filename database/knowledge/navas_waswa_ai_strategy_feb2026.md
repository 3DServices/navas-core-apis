# Navas Waswa AI strategy Feb2026

<!-- page 1 -->
Tim Mwandha From: Tim Mwandha <timothy@3dservices.co.ug> Sent: 19 February 2026 01:22 To: 'eric.lukyamuzi@3dservices.co.ug' Cc: '3dmancom@3dservices.co.ug' Subject: NAVAS - AI Agent - Cost Strategy Eric, Read this – about managing costs of Waswa AI; I have re-structured our NAVAS IoT offering. AI agents will have a big role. What's the point of building a platform that will soon be obsolete (the one without AI); Therefore, AI integration is at core level of Navas by design; and for this reason we need to be cost sensitive by design as well. CEO. XXXXXXXX For a high-compute platform like NAVAS COCKPIT , which manages 150,000+ units with real-time "Waswa AI" intervention, the most effective strategy isn't a single choice—it is a Hybrid "Cascading" Architecture . To keep costs down while maintaining sub-second latency for telematics events, you must move away from a "One-Size- Fits-All" AI model.

## 1. The Three Tiers of AI Execution

Approach Ideal Use Case Cost Profile Risk Complex reasoning, high-level PAYG External APIs Rate limits & high financial audits, monthly ROI High (Per 1k tokens) (GPT-4o, Claude 3.5) latency. reports. Hosted Open-Source Intermediate tasks: Maintenance & Medium (Fixed (Llama 3, Mistral on your SMS/WhatsApp sentiment GPU hardware GPU/Server cost) server) analysis, daily log summaries. costs. Edge/On-Device SLM Real-time alerts: Speeding, Harsh Low (Compute Limited reasoning (Small Language Models Braking, Geofencing, Fuel theft included in server capacity. / Local Python) detection. overhead)

## 2. Recommended Strategy: The "AI Cascade" Model

The most cost-effective way to run AI for NAVAS is to use a Router-Based Strategy . Instead of sending every packet to an expensive external LLM, use this hierarchy:

<!-- page 2 -->
Tier 1: The Local "Behavioral" Engine (Python Scripts)  What: Vanilla Python logic (as per your tech stack).  Role: 90% of your AI work (monitoring speed, fuel levels, and geofences) should be done here. This is "Zero Cost" AI.  Action: If a parameter is normal, stop there. If an anomaly is detected, escalate. Tier 2: The Self-Hosted SLM (Mistral-7B / Llama 3 on Local Server)  What: Run a Small Language Model (SLM) on your own infrastructure (Nvidia A10 or L4 GPUs).  Role: Contextualizing alerts. Instead of a raw "Fuel Drop" alert, the local SLM looks at the context (Is the engine off? Is it at a known depot?) and writes a concise WhatsApp alert.  Cost Saving: You pay for the server, not the number of messages. Tier 3: The External "Super-Brain" (GPT-4o API)  What: PAYG API.  Role: High-value executive functions. Use this only for the "Revenue Hub" (EBITDA analysis) or "Accident Reconstruction" where legal-grade reasoning is required.  Cost Control: Use this for less than 1% of total system transactions.

## 3. Strategic "Cost-Killers" for NAVAS

1. Semantic Caching (Redis): If Waswa AI answers a question for one fleet manager (e.g., "What is the average idle time?"), cache that answer in Redis . If another manager asks the same thing, serve the cached answer for $0$ cost instead of re-running the LLM. 2. Prompt Token Stripping: Telematics data is "noisy." Use your Python Sockets to strip out useless metadata before sending a packet to an AI agent. Reducing the "Context Window" by 50% reduces your API bill by 50%. 3. Batch Processing: For non-critical tasks (e.g., weekly driver scorecards), don't run them in real-time. Batch 1,000 units together and send them as a single file to the AI at 3:00 AM when API rates are sometimes cheaper or when server load is low. 4. Fine-Tuning a "Thin" Model: Instead of using a general-purpose LLM, fine-tune a small model specifically on your Telematics Parameter List . A fine-tuned 7B model will outperform a generic 175B model for IoT tasks at a fraction of the cost.

## Final Recommendation

For the NAVAS COCKPIT , you should host your own LLM (Llama 3 or Phi-3) on a dedicated GPU server for the majority of "Waswa" interactions, while keeping a PAYG API as a backup for complex "Super-Admin" inquiries. Would you like me to draft a technical cost-comparison sheet for hosting an LLM on an AWS EC2 instance vs. using the OpenAI API for 50,000 units? To provide a strategic roadmap for the NAVAS COCKPIT v26.0 , we must compare the fiscal impact of scaling AI agents for 50,000 active units. The primary cost driver in telematics AI isn't the storage of data, but the Inference Cost (the "thinking" tax) applied to the millions of packets flowing through your Cassandra/Kafka pipeline.

<!-- page 3 -->
## Cost Comparison: AI Agency at Scale (50,000 Units)

This comparison assumes each unit generates 10 "Critical Events" per day (e.g., ignition, geofence, harsh braking, fuel drop) that require Waswa AI to analyze and generate a summary or notification. Total Daily Inference Requests: 500,000 . Feature External PAYG API (e.g., GPT-4o-mini) Self-Hosted LLM (e.g., Llama 3 on AWS EC2) Pricing Model $ per 1M Tokens (Input + Output) Monthly Flat Rate (Instance + GPU) Daily Cost Est. $75.00 (Avg. $0.15 per 1k units/day) $16.50 (g5.2xlarge Spot Instance) Monthly Cost $2,250.00 $495.00 Latency 1.5s – 4s (Network + API Queue) < 500ms (Local Backbone) Data Privacy Data leaves NAVAS local network Data stays in your VPC Scalability Infinite, but costs scale linearly Limited by GPU VRAM; requires clusters Best For Prototyping & High-Level Financials Real-time Dispatch & Fleet Health

## The "NAVAS" Strategic Recommendation

As your Lead Architect, I recommend the Self-Hosted Hybrid Model to achieve the 78% cost reduction shown above.

## 1. The Local Infrastructure (The "Heavy Lifter")

Deploy a Llama-3-8B or Mistral-7B model on an AWS g5.2xlarge (NVIDIA A10G) instance.  Why: At 50,000 units, your traffic is consistent. You are paying for the GPU "idling" time anyway, so running 500k requests through it costs the same as running 50k.  Optimization: Use vLLM or NVIDIA TensorRT-LLM libraries to increase throughput. This allows one single server to handle thousands of concurrent "Waswa" requests.

## 2. The Tokenized API (The "Expert Witness")

Keep GPT-4o via API for only two specific modules:  Revenue Hub: When an Admin asks for complex EBITDA projections.  Legal/Audit: Generating irrefutable accident reconstruction reports.  Impact: This limits your variable "per-token" costs to less than $50/month .

## 3. Semantic Caching (The "Zero-Cost" Layer)

Implement a Vector Cache in your Redis DB .

<!-- page 4 -->
 Logic: If Waswa AI analyzes a "Low Battery" event for a Piki in Kampala at 9:00 AM, the reasoning is likely identical for a Piki in Nairobi at 9:05 AM.  Action: Check Redis for a similar "Context Hash" before hitting the LLM. If it exists, serve the previous response. Cost: $0.00.

## Implementation Roadmap

1. Phase 1 (Hybrid): Start with GPT-4o-mini (External) for all Waswa notifications to refine the "Prompt Engineering." 2. Phase 2 (Migration): Once prompts are stable, "Distill" that knowledge into a local Llama 3 model hosted on your Ubuntu/NAVAS.local environment. 3. Phase 3 (Optimization): Use the Token Engine logic to charge customers more for "External AI" requests (Deep Insights) vs. "Local AI" (Standard Alerts). Would you like me to generate the Python code for a "Semantic Router" that decides whether a fleet alert should go to the cheap Local LLM or the expensive External API?
