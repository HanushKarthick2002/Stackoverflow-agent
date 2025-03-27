import subprocess
import sys

# Install required packages if missing
required_packages = ["requests", "beautifulsoup4", "rich","urllib3"]

def install_missing_packages():
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            print(f"Installing missing package: {package}")
            subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)

install_missing_packages()

import os
import requests
import warnings
import json
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
import re
import time

# Suppress HTTPS warnings
warnings.simplefilter("ignore", InsecureRequestWarning)

console = Console()

def search_answers(query, num_results=5):
    """Search Stack Overflow for answers matching the query."""
    search_url = "https://api.stackexchange.com/2.3/search/advanced"
    params = {
        "order": "desc",
        "sort": "relevance",
        "q": query,
        "site": "stackoverflow",
        "accepted": "True",
        "filter": "withbody"
    }
    response = requests.get(search_url, params=params, verify=False)
    data = response.json()

    if "items" not in data or len(data["items"]) == 0:
        return []

    question_ids = [item["question_id"] for item in data["items"][:num_results]]
    return question_ids

def get_top_answers_for_questions(question_ids, num_answers=3):
    """Retrieve top answers from Stack Overflow for given question IDs, displaying progress."""
    all_answers = []

    with Live("", console=console, refresh_per_second=10) as live:
        for qid in question_ids:
            url = f"https://api.stackexchange.com/2.3/questions/{qid}/answers"
            params = {
                "order": "desc",
                "sort": "votes",
                "site": "stackoverflow",
                "filter": "withbody"
            }
            response = requests.get(url, params=params, verify=False)
            data = response.json()

            if "items" in data and len(data["items"]) > 0:
                for answer in data["items"][:num_answers]:
                    soup = BeautifulSoup(answer['body'], "html.parser")
                    cleaned_answer = soup.get_text(separator="\n").strip()
                    all_answers.append((answer['score'], cleaned_answer, answer['body']))

                    # Display each fetched answer immediately
                    live.update(Panel(f"[bold yellow]Fetched Answer (Votes: {answer['score']}):[/bold yellow]\n{cleaned_answer}", expand=False))
                    time.sleep(0.5)

    return all_answers[:num_answers]

def stream_llm_response(question, answers):
    """Stream LLM response in real time."""
    formatted_answers = "\n\n".join([f"Answer {i+1} (Votes: {votes}):\n{content}" for i, (votes, content, raw) in enumerate(answers)])

    llm_api_url = "https://llmfoundry.straive.com/openai/v1/chat/completions"
    llm_headers = {
        "Authorization": f"Bearer {os.environ.get('LLMFOUNDRY_TOKEN', '')}:my-test-project",
        "Content-Type": "application/json"
    }
    llm_payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": f"""
            You are an expert in simplifying technical content while maintaining accuracy. Given a technical question and several extracted answers from Stack Overflow, your task is to combine and present them in a clear, easy-to-understand manner without altering their core meaning.

Instructions:
- Summarize key insights from all answers into a single, well-structured response.
- Ensure clarity by avoiding unnecessary jargon while preserving technical accuracy.
- If the answers contain code, format it neatly and add brief explanations if needed.
- If multiple solutions exist, present them logically and indicate any differences or trade-offs.
- Keep the response concise but informative, ensuring completeness.

            **Input:**
            Question: {question}
            Extracted Answers: 
            {formatted_answers}
            """
            }
        ],
        "stream": True
    }

    response = requests.post(llm_api_url, headers=llm_headers, json=llm_payload, stream=True)

    console.print(Panel("[bold green]Streaming LLM Response...[/bold green]", title="LLM Output", expand=False))

    llm_answer = ""
    with Live("", console=console, refresh_per_second=10) as live:
        for chunk in response.iter_lines():
            if chunk:
                try:
                    cleaned_chunk = chunk.decode("utf-8").strip()
                    if cleaned_chunk.startswith("data: "):
                        cleaned_chunk = cleaned_chunk[6:].strip()

                    decoded_chunk = json.loads(cleaned_chunk)

                    if "choices" in decoded_chunk and decoded_chunk["choices"]:
                        delta = decoded_chunk["choices"][0].get("delta", {})
                        content_piece = delta.get("content", "")

                        if content_piece:
                            llm_answer += content_piece
                            live.update(Panel(f"[bold green]LLM Response:[/bold green]\n{llm_answer}", expand=False))
                            time.sleep(0.05)

                except json.JSONDecodeError:
                    console.print("[bold red]⚠️ Warning: Received an invalid JSON response from LLM.[/bold red]")
                    continue

    return llm_answer

def display_results(question, question_ids, answers):
    """Display retrieved answers and final LLM response."""
    console.print(Panel(f"[bold cyan]Question:[/bold cyan] {question}", expand=False))

    if not question_ids:
        console.print("[bold red]No relevant solutions found![/bold red]")
        return

    console.print(Panel(f"[bold magenta]Fetching top {len(answers)} answers from Stack Overflow...[/bold magenta]", expand=False))

    llm_answer = stream_llm_response(question, answers)

    console.print(Panel("[bold green]Final LLM Answer:[/bold green]", title="LLM Response", expand=False))
    console.print(llm_answer)

    save_to_file(question, question_ids, answers, llm_answer)

def save_to_file(question, question_ids, answers, llm_answer):
    """Save retrieved responses to a file."""
    filename = "stackoverflow_solutions.txt"
    with open(filename, "w", encoding="utf-8") as file:
        file.write(f"Question: {question}\n")
        file.write(f"Stack Overflow Question IDs: {', '.join(map(str, question_ids))}\n\n")

        for i, (votes, stackoverflow_answer, raw_stackoverflow_answer) in enumerate(answers):
            file.write(f"Answer {i+1} (Votes: {votes}):\n")
            file.write(stackoverflow_answer + "\n\n")

        file.write("LLM Simplified Answer:\n")
        file.write(llm_answer + "\n")

    console.print(f"[bold cyan]Results saved to {filename}[/bold cyan]")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[bold red]Usage:[/bold red] python question.py 'your question here'", style="bold red")
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    question_ids = search_answers(question, num_results=5)
    answers = get_top_answers_for_questions(question_ids, num_answers=3)

    if not answers:
        console.print("[bold red]No solutions found on Stack Overflow.[/bold red]")
    else:
        display_results(question, question_ids, answers)
