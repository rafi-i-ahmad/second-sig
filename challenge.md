
Build with Gemini 4 Argon (gemini-4-argon): Autonomous Agents & Multimodal Applications
Google DeepMind logo
Supported by Google DeepMind
1st Place($7,000)
$7,000 in Gemini API credits
2nd Place($5,000)
$5,000 in Gemini API credits
3rd Place($3,000)
$3,000 in Gemini API credits
Build a working application or autonomous agent powered by Gemini 4 Argon (gemini-4-argon), Google DeepMind's new frontier model for software engineering, complex knowledge work, cybersecurity defense and multimodal creation, that solves a specific problem for a real person you can name.

Gemini 4 Argon unifies input, reasoning and output in a single 1M-token context window. It works longer on its own, retains context across large codebases and dense document sets, and pairs as a lead orchestrator with Antigravity Managed Agents and fast companion models for parallel subagents, real-time voice and vision, image, video and music generation, and on-device open models.

Your challenge
Build and demo a working project that could only be built with Gemini 4 Argon and Google DeepMind's latest model toolkit. You can build in any domain, including Encode London's themes:

Pathway 1: Autonomous Agents That Ship (software engineering, cybersecurity and complex workflows). Build an agent that plans, uses tools, verifies its own output against a concrete pass/fail signal (test suites, compiler output, runtime logs or headless browser checks), and finishes multi-step work end to end, using gemini-4-argon (thinking_level "medium" or "high", long decode with background=True) or inside a Google-hosted Linux sandbox with antigravity-preview-09-2026.
Ideas: a self-healing security and dependency migration agent that reproduces a vulnerability in an Antigravity sandbox, patches it and outputs a visual diff walkthrough; a legacy codebase modernizer that rebuilds a tested modern web app from an old app and a screen recording; a research-to-prototype system where Argon coordinates the Deep Research agent and delegates modules to gemini-3.8-flash subagents.
Pathway 2: The Real World, Hard Tech & Multimodal Creation (voice, video, 3D/WebGPU and physical systems). Build an application that perceives, simulates or creates across real-world video, live voice, spatial 3D/WebGPU environments, or hardware and scientific data, using gemini-4-argon and companion models.
Ideas: a playable Three.js/WebGPU world where Argon computes the physics or level geometry while gemini-3.8-live powers voice interaction and lyria-3.5 drives the soundtrack; a manufacturing or lab root-cause analyst that scrubs inspection footage alongside sensor CSVs and long datasheets; a hands-free voice and screen navigator in 70+ languages with human confirmation before any form is submitted.
Prizes: $15,000 in Gemini API / Google Cloud credits
1st place: $7,000 in Gemini API credits
2nd place: $5,000 in Gemini API credits
3rd place: $3,000 in Gemini API credits
Judging criteria
Judges score live working demos, not slide decks (3-minute live demo plus 2 minutes of Q&A).

Working live demo (50%): does it run live with real inputs in under 3 minutes? Did the team use gemini-4-argon, Managed Agents or companion models effectively, with a real verification loop?
Problem and usefulness (25%): does it solve a concrete problem for a specific person you can name? Could it grow into a product or open-source tool people use after the hackathon?
Originality / needed Gemini 4 Argon (15%): is it only possible because of Argon's 1M unified context, long decode, frontier reasoning, agentic video analysis, 3D/WebGPU generation or multi-agent orchestration? Does it keep people in control of actions that affect external systems, money or private data?
Clarity of pitch (10%): did the team show who the user is and demo the working product clearly in 3 minutes, without slides?
Projects to avoid (disqualified or low-scoring)
A basic chat wrapper or simple Q&A bot over a single PDF.
A static page with no autonomous reasoning, verification loop or multimodal workflow.
An unverified medical diagnosis, mental health counselling or financial advice bot without human-in-the-loop safeguards.
Anything built before kickoff. Open-source libraries and starter templates are fine, but your demo must only show code written during the hackathon.
Who it's for
Builders of all experience levels: from first-time makers prototyping full-stack apps in Google AI Studio Build and Google Antigravity, to AI and systems engineers building autonomous multi-agent workflows with the Interactions API.

Your toolkit
Lead reasoning, coding, 3D/WebGPU and orchestration: gemini-4-argon
Autonomous sandbox execution: antigravity-preview-09-2026 (Antigravity Managed Agent)
Fast parallel subagents and routing: gemini-3.8-flash, gemini-3.5-flash-lite
Deep web research with citations: deep-research-preview-04-2026
Real-time voice, camera, transcription and translation: gemini-3.8-live, gemini-3.8-live-extended-thinking, gemini-3.5-transcribe-live, gemini-3.5-live-translate-preview, gemini-3.8-flash-tts
Images, video with sound and music: gemini-nano-banana-2.1, gemini-omni-1.1-flash, lyria-3.5
Open models, cloud or on-device: gemma-4-31b-it (plus the local E2B and E4B sizes)
Use the official Gemini SDKs, version 2.3.0 or later: Python (pip install -U "google-genai>=2.3.0") or TypeScript/JavaScript (npm install @google/genai@latest). The recommended endpoint is the Interactions API (client.interactions.create), which covers models and managed agents, keeps server-side state and supports long background runs.

Get started in 15 minutes
Claim your credits: collect your pre-provisioned account or Gemini API credits from the Google DeepMind team at kickoff.
Give your coding agent the Gemini API skills, so it writes current gemini-4-argon and Interactions API code: npx skills add google-gemini/gemini-skills --skill gemini-api-dev and npx skills add google-gemini/gemini-skills --skill gemini-live-api-dev (or agy plugin install https://github.com/google-gemini/gemini-skills in Antigravity). Or prototype directly in Google AI Studio Build or Google Antigravity.
Check the Argon API rules: use thinking_level ("low", "medium" by default, or "high") instead of the deprecated thinking_budget; remove temperature, top_p, top_k and explicit cached_content (implicit caching is automatic); and set background=True to generate past 65,536 tokens (up to 1M).
Ask the Google DeepMind mentors onsite (Amit Vadi and Geneviève Huskens, at the Google DeepMind booth) whenever you hit a blocker.
Workshop
Build with Gemini 4 Argon: Autonomous Agents, Long-Horizon Coding & Multimodal Apps, Friday 23 October at 2:30pm. A 30-minute practical session on Argon's 1M-token context and long decode, autonomous coding and verification loops with Antigravity Managed Agents, multi-agent and multimodal orchestration, and a live Q&A and bounty walkthrough, including how to claim your credits and structure your 3-minute demo.

Submission requirements
A GitHub repository.
A 3-minute demo video, plus a live demo for the judges.
In your submission, say which Gemini models and agents you used and how.
Resources
Gemini 4 Argon developer guide
Gemini 4 Argon interactive showcase
Google AI Studio and AI Studio Build
Google Antigravity
Gemini API skills for coding agents
Gemini API documentation and cookbook
Live API starter apps
Tell the Google DeepMind team what worked, what broke and what you wish existed, in person or at gemini-developer-feedback@google.com.

__

Agents That Ship
Encode Club logo
Supported by Encode Club
Build an AI agent that does a real job end to end, not just a chatbot.

Pick a task someone does today by hand, in a spreadsheet or across ten browser tabs, and build an agent that sees it through: it gathers what it needs, uses real tools, makes decisions, recovers when something goes wrong and delivers a finished result. A person should stay in control where it matters, approving the risky steps rather than doing the work.

What to build
Any domain is welcome. Some ideas to get you started:

Small-business operations: chase unpaid invoices, reconcile payments, reorder stock or book suppliers.
Recruiting: screen applications against a brief, shortlist candidates and schedule interviews.
Research: produce a sourced brief, competitor report or due-diligence pack, checking its own claims before it hands anything over.
Event running: find a venue, set up the event page, manage sign-ups and send reminders and follow-ups.
Developer: take an issue, write the fix, run the tests and open a pull request ready for review.
Personal admin: renewals, refunds, complaints, forms and appointments.
Agents that work together: agents that hand tasks to each other, or pay and get paid for work, for example with stablecoins.
Judging criteria
Does the job: it completes a real task from start to finish with minimal hand-holding.
Reliability: it handles errors and edge cases, and knows when to stop and ask a human.
Usefulness: someone would actually use it, or pay for it.
Technical depth: good use of tools, memory, planning and evaluation.
Safety and control: sensible permissions, approval steps for risky actions and a clear record of what the agent did.
Submission requirements
A working demo of the agent completing its task from start to finish, live or recorded.
A code repository with a README and setup instructions.
A 2–4-minute demo video.
A short description of the agent's tools, the steps it takes and where a human approves.