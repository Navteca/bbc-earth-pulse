# Earth Pulse MCP
## A Planetary Intelligence System Built on BBC News + GPT 5.4

Version: 1.0  
Authoring Goal: Build an MCP server that feels like an AI observing humanity in real time.

---

# Table of Contents

1. Vision
2. Philosophy
3. Why This Product Matters
4. What Makes It Different
5. Product Experience
6. Core Capabilities
7. Example User Questions
8. User Stories
9. System Architecture
10. Technology Stack
11. Data Sources
12. Ingestion Layer
13. AI Enrichment Layer
14. Temporal Intelligence
15. Narrative Intelligence
16. MCP Server Design
17. MCP Tools
18. Suggested Database Schema
19. Example Prompts
20. Example Outputs
21. Emotional Taxonomy
22. Topic Taxonomy
23. Future Features
24. Build Phases
25. Implementation Plan
26. Risks & Constraints
27. Design Principles
28. Final Product Goal

---

# 1. Vision

Earth Pulse is not a news application.

It is an AI-powered planetary intelligence system that continuously interprets the emotional, geopolitical, technological, and societal state of humanity using BBC journalism as its sensory input.

The system transforms raw journalism into:
- emotional intelligence
- civilization-scale pattern recognition
- narrative evolution
- geopolitical interpretation
- societal mood analysis
- temporal awareness

The purpose is not monetization.

The purpose is:
# the wow effect.

The user should feel:
> “This AI understands what is happening to humanity right now.”

---

# 2. Philosophy

Most systems answer questions.

Earth Pulse interprets civilization.

This distinction is critical.

Do NOT build:
- a chatbot
- a news summarizer
- a feed reader
- a headline retrieval engine

Build:
# an interface to collective human consciousness.

---

# 3. Why This Product Matters

Modern humans are overwhelmed with information.

People do not actually want:
- more notifications
- more headlines
- more links

People want:
- What matters?
- Why does it matter?
- What changed?
- What patterns are emerging?
- What should I pay attention to?
- Is the world becoming more hopeful or more anxious?

Earth Pulse answers those questions.

---

# 4. What Makes It Different

Most AI systems:
- retrieve information

Earth Pulse:
- synthesizes civilization-level meaning

Most news systems:
- show isolated stories

Earth Pulse:
- explains the emotional and geopolitical atmosphere of Earth

Most dashboards:
- display metrics

Earth Pulse:
- interprets humanity

---

# 5. Product Experience

The product should feel:
- cinematic
- philosophical
- calm
- intelligent
- reflective
- globally aware

It should NOT feel like:
- Google News
- Perplexity
- RSS aggregation
- doomscrolling
- a generic chatbot

The emotional experience matters as much as the technical implementation.

---

# 6. Core Capabilities

The system should be capable of:

## Global Mood Analysis
Understanding humanity’s emotional atmosphere.

## Narrative Evolution
Tracking how stories evolve over weeks, months, and years.

## Trend Acceleration Detection
Identifying topics rapidly increasing in importance.

## Regional Emotional Analysis
Comparing emotional climates across regions.

## Historical Contextualization
Explaining how current situations emerged.

## Civilization Reflection
Helping users understand the collective concerns of humanity.

---

# 7. Example User Questions

## Planetary Awareness

- “What changed in the world today?”
- “What is humanity worried about right now?”
- “What stories are dominating global attention?”
- “What tensions are increasing?”

---

## Emotional Intelligence

- “What is the emotional mood of Europe?”
- “Is global anxiety increasing?”
- “What emotions dominate technology news?”
- “How does Asia emotionally compare to North America?”

---

## Narrative Evolution

- “How did AI fear evolve?”
- “How has climate anxiety changed since 2023?”
- “When did inflation become a dominant narrative?”
- “What are the turning points in the Ukraine conflict?”

---

## Civilization Reflection

- “Is humanity becoming more hopeful?”
- “What fears dominate modern society?”
- “What signs of optimism appeared this week?”
- “What is humanity collectively obsessed with right now?”

---

# 8. User Stories

## Story 1 — Global Awareness

As a user,  
I want to ask:
> “What changed in the world today?”

So that I can quickly understand the global state of humanity.

---

## Story 2 — Emotional Understanding

As a user,  
I want to ask:
> “What is the emotional mood of Europe?”

So that I can understand societal anxiety and optimism trends.

---

## Story 3 — Historical Narrative

As a user,  
I want to ask:
> “How has AI coverage evolved over the last 3 years?”

So that I can understand narrative progression.

---

## Story 4 — Regional Comparison

As a user,  
I want to compare:
> “Europe vs Asia emotional climate”

So that I can understand geopolitical differences emotionally.

---

## Story 5 — Humanity Reflection

As a user,  
I want to ask:
> “Is humanity becoming more hopeful?”

So that I can reflect on civilization-level trends.

---

## Story 6 — Emerging Tensions

As a user,  
I want to ask:
> “What tensions appear to be escalating?”

So that I can understand momentum without prediction.

---

# 9. System Architecture

text BBC RSS/API     ↓ Ingestion Layer     ↓ Normalization Pipeline     ↓ AI Enrichment Layer     ↓ Temporal Database     ↓ Narrative Intelligence Layer     ↓ MCP Server     ↓ User 

---

# 10. Technology Stack

## Backend
- Python 3.12+
- FastAPI

## MCP
- Official MCP SDK
- SSE transport
- stdio transport optional

## AI Models
- GPT 5.4
- GPT 5.4-mini for enrichment

## Embeddings
- text-embedding-3-large
OR
- text-embedding-3-small

## Database
MVP:
- SQLite

Production:
- PostgreSQL

Optional:
- pgvector

## Scheduling
- APScheduler
OR
- Celery + Redis

## Deployment
- Docker
- Railway
- Render
- Fly.io

## Frontend (Optional)
- Next.js
- Tailwind
- D3.js
- Globe visualizations

---

# 11. Data Sources

## Official BBC Resources

### BBC Developer Portal
https://developer.bbc.com/

### BBC RSS Feeds
https://support.bbc.co.uk/platform/feeds/NewsFeeds.htm

### BBC NEWSHUB API
https://docs.newshub.bbc.co.uk/reference/index.html

---

## Unofficial API

### BBC News API
https://bbc-news-api.vercel.app/

GitHub:
https://github.com/Sayad-Uddin-Tahsin/BBC-News-API

---

# 12. Ingestion Layer

The ingestion system continuously pulls:
- RSS feeds
- BBC APIs
- regional feeds
- topic feeds

## Poll Frequency
- every 5 minutes
OR
- every 15 minutes

## Store
- title
- summary
- content
- URL
- timestamp
- region
- category
- source

## Required Features
- deduplication
- retry handling
- feed normalization
- timestamp normalization

---

# 13. AI Enrichment Layer

Every article should be enriched using GPT 5.4-mini.

---

## Emotional Classification

Possible emotions:
- anxiety
- optimism
- fear
- tension
- hope
- uncertainty
- celebration
- instability
- resilience

---

## Topic Classification

Examples:
- AI
- economy
- elections
- climate
- war
- labor
- healthcare
- energy
- technology

---

## Narrative Classification

Examples:
- escalation
- disruption
- innovation
- recovery
- polarization
- stabilization

---

## Scoring System

Generate normalized scores:
- urgency_score
- anxiety_score
- optimism_score
- conflict_score
- stability_score

Range:
0.0 → 1.0

---

## Example Enriched Article

json {   "title": "Oil prices surge after attacks",   "emotion": "anxiety",   "region": "Middle East",   "topics": ["energy", "conflict"],   "urgency_score": 0.82,   "optimism_score": 0.11,   "conflict_score": 0.91 } 

---

# 14. Temporal Intelligence

This is the most important component.

Most systems know:
> what exists now

Earth Pulse knows:
- what changed
- what accelerated
- what disappeared
- what emerged
- what repeated
- what emotionally shifted

THIS creates the intelligence illusion.

---

## Examples

### Trend Acceleration
> “AI labor disruption stories increased 240% this week.”

### Narrative Shift
> “AI coverage shifted from innovation toward labor anxiety.”

### Emotional Change
> “European reporting became significantly more anxious after energy instability.”

---

# 15. Narrative Intelligence

The LLM layer synthesizes:
- emotional atmosphere
- geopolitical movement
- societal concerns
- technology narratives
- macro-patterns
- historical trajectories

---

## Design Rule

DO NOT summarize headlines.

Instead:
- interpret humanity
- synthesize patterns
- explain emotional movement
- contextualize change

---

# 16. MCP Server Design

The MCP server exposes civilization-level intelligence tools.

The MCP should feel:
- calm
- intelligent
- thoughtful
- observant
- globally contextualized

Avoid:
- sensationalism
- certainty
- alarmism
- predictions

---

# 17. MCP Tools

# get_global_mood()

Returns:
- dominant emotions
- emotional shifts
- global mood

Example:
> “What is humanity worried about today?”

---

# summarize_world_changes(hours)

Summarizes major global changes.

Example:
> “What changed on Earth in the last 24 hours?”

---

# compare_regions(region_a, region_b)

Compares emotional and geopolitical atmosphere.

Example:
> “Compare Europe and Asia emotionally.”

---

# timeline(topic)

Builds historical narrative evolution.

Example:
> “How has AI coverage evolved since 2022?”

---

# emerging_topics()

Detects rapidly increasing narratives.

Example:
> “What topics are accelerating globally?”

---

# humanity_focus()

Returns humanity’s dominant collective concerns.

Example:
> “What are humans collectively obsessed with right now?”

---

# emotional_heatmap()

Returns regional emotional states.

Example:
- Europe → anxiety
- Asia → caution
- Africa → optimism growth

---

# narrative_shift_detector()

Detects framing changes.

Example:
> “Climate reporting shifted from warning toward adaptation.”

---

# 18. Suggested Database Schema

## Articles Table

sql CREATE TABLE articles (     id TEXT PRIMARY KEY,     title TEXT,     summary TEXT,     content TEXT,     region TEXT,     category TEXT,     source TEXT,     url TEXT,     published_at TIMESTAMP ); 

---

## Enrichment Table

sql CREATE TABLE enrichments (     article_id TEXT,     emotion TEXT,     topics JSON,     narratives JSON,     urgency_score FLOAT,     anxiety_score FLOAT,     optimism_score FLOAT,     conflict_score FLOAT,     stability_score FLOAT ); 

---

## Embeddings Table

sql CREATE TABLE embeddings (     article_id TEXT,     embedding VECTOR ); 

---

# 19. Example Prompts

## Global Mood Prompt

text You are analyzing the emotional and geopolitical state of humanity using BBC journalism.  Analyze: - dominant emotions - emerging anxieties - optimism signals - geopolitical movement - technology narratives - societal focus  Write clearly, intelligently, calmly, and philosophically.  Avoid sensationalism. 

---

## Regional Comparison Prompt

text Compare the emotional atmosphere of Europe and Asia using recent reporting.  Focus on: - anxiety - optimism - economic outlook - geopolitical tension - technological momentum 

---

# 20. Example Outputs

## Example 1

### User
> “What is humanity worried about today?”

### Response
> “Global anxiety is currently centered around economic instability, geopolitical escalation, and the long-term effects of artificial intelligence on labor markets.
>
> European coverage increasingly reflects energy insecurity and economic caution, while Asian reporting shows heightened attention toward manufacturing slowdown and regional power dynamics.
>
> Technology reporting remains optimistic overall, but labor anxiety surrounding AI automation has accelerated sharply during the last week.”

---

## Example 2

### User
> “How has AI coverage evolved?”

### Response
> “AI coverage evolved through three dominant phases:
>
> 1. Curiosity and experimentation
> 2. Competitive acceleration
> 3. Labor and regulatory anxiety
>
> Recent reporting increasingly frames AI as a societal restructuring force rather than merely a technological innovation.”

---

## Example 3

### User
> “What changed on Earth today?”

### Response
> “The global emotional atmosphere became more cautious during the last 24 hours.
>
> Energy market instability increased anxiety across Europe and Asia, while technological optimism rose following several major AI infrastructure announcements.
>
> Climate-related reporting intensified across multiple regions, particularly surrounding extreme weather resilience.”

---

# 21. Emotional Taxonomy

Recommended emotions:
- anxiety
- optimism
- fear
- uncertainty
- resilience
- hope
- instability
- caution
- confidence
- tension
- inspiration
- exhaustion
- polarization

---

# 22. Topic Taxonomy

Recommended categories:
- AI
- labor
- economy
- climate
- war
- elections
- healthcare
- energy
- science
- technology
- culture
- migration
- geopolitics
- security
- education

---

# 23. Future Features

## Emotional Globe Visualization
Interactive Earth visualization showing:
- emotional hotspots
- geopolitical tension
- optimism regions

---

## Narrative Timelines
Animated evolution of:
- AI anxiety
- climate fear
- economic optimism
- geopolitical instability

---

## Civilization Dashboard
Live:
- global mood
- narrative acceleration
- societal focus
- emotional momentum

---

## Audio Narration
AI-generated:
> “Today on Earth…”

---

## Multi-Source Expansion
Eventually include:
- Reuters
- Al Jazeera
- Financial Times
- AP News
- scientific journals

---

# 24. Build Phases

# Phase 1 — MVP

Build:
- RSS ingestion
- SQLite storage
- GPT enrichment
- MCP server
- basic temporal analysis

Goal:
working intelligence prototype

---

# Phase 2 — Intelligence

Add:
- embeddings
- semantic retrieval
- regional analysis
- emotional heatmaps
- narrative timelines

Goal:
planetary intelligence system

---

# Phase 3 — Cinematic Experience

Add:
- world visualizations
- live dashboards
- animated emotional movement
- storytelling interface
- audio narration

Goal:
AI civilization interface

---

# 25. Implementation Plan

## Week 1
- RSS ingestion
- database setup
- enrichment pipeline

## Week 2
- temporal intelligence
- trend acceleration
- MCP tools

## Week 3
- narrative synthesis
- emotional analysis
- regional comparisons

## Week 4
- polish
- prompt tuning
- testing
- deployment

---

# 26. Risks & Constraints

## Avoid Prediction
Do NOT:
- predict wars
- predict elections
- claim certainty

Instead:
- discuss momentum
- discuss emerging trends
- discuss emotional movement

---

## Avoid Sensationalism
The system must remain:
- calm
- grounded
- analytical

---

## Avoid Hallucinations
All synthesis must derive from:
- actual journalism
- observable trends
- measurable changes

---

# 27. Design Principles

# Principle 1
Interpret humanity, not headlines.

---

# Principle 2
Prioritize synthesis over retrieval.

---

# Principle 3
Emotional intelligence matters more than volume.

---

# Principle 4
Temporal awareness creates intelligence illusion.

---

# Principle 5
The tone should feel philosophical, not dramatic.

---

# 28. Final Product Goal

Earth Pulse should not feel like:
> “AI reading the news.”

It should feel like:
# “AI observing humanity in real time.”

The user should leave the interaction feeling:
- more aware
- more reflective
- more connected to the state of civilization
- slightly amazed

That is the actual product.
