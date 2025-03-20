import subprocess
import sys

# List of required packages
required_packages = [
    "requests",
    "beautifulsoup4",
    "rich"
]

# Function to install missing packages
def install_missing_packages():
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            print(f"Installing missing package: {package}")
            subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)

# Install dependencies before running the script
install_missing_packages()

import os
import sys
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

def get_question_id(question):
    search_url = "https://api.stackexchange.com/2.3/search/advanced"
    params = {
        "order": "desc",
        "sort": "relevance",
        "q": question,
        "site": "stackoverflow"
    }
    response = requests.get(search_url, params=params, verify=False)
    data = response.json()

    if "items" in data and len(data["items"]) > 0:
        return data["items"][0]["question_id"]
    else:
        return None

def get_top_answers(question, num_answers=3):
    question_id = get_question_id(question)
    if not question_id:
        return None, []

    url = f"https://api.stackexchange.com/2.3/questions/{question_id}/answers"
    params = {
        "order": "desc",
        "sort": "votes",
        "site": "stackoverflow",
        "filter": "withbody"
    }
    response = requests.get(url, params=params, verify=False)
    data = response.json()

    answers = []
    if "items" in data and len(data["items"]) > 0:
        for i, answer in enumerate(data["items"][:num_answers]):
            soup = BeautifulSoup(answer['body'], "html.parser")
            cleaned_answer = soup.get_text(separator="\n").strip()
            answers.append((answer['score'], cleaned_answer, answer['body']))

    return question_id, answers

import json
import os
import time
import requests
from rich.console import Console
from rich.live import Live
from rich.panel import Panel

console = Console()

import json
import os
import time
import requests
from rich.console import Console
from rich.live import Live
from rich.panel import Panel

console = Console()

def stream_llm_response(question, answers):
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
            You are an expert in simplifying technical content while maintaining accuracy. Given a technical question and three extracted answers from Stack Overflow, your task is to combine and present them in a clear, easy-to-understand manner without altering their core meaning.

Instructions:

Summarize key insights from all three answers into a single, well-structured response.
Ensure clarity by avoiding unnecessary jargon while preserving technical accuracy.
If the answers contain code, format it neatly and add brief explanations if needed.
If multiple solutions exist, present them logically and indicate any differences or trade-offs.
Keep the response concise but informative, ensuring completeness.
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
    with Live("") as live:
        for chunk in response.iter_lines():
            if chunk:
                try:
                    # Remove "data: " prefix if present
                    cleaned_chunk = chunk.decode("utf-8").strip()
                    if cleaned_chunk.startswith("data: "):
                        cleaned_chunk = cleaned_chunk[6:].strip()

                    # Parse JSON
                    decoded_chunk = json.loads(cleaned_chunk)

                    # Extract and display content
                    if "choices" in decoded_chunk and decoded_chunk["choices"]:
                        delta = decoded_chunk["choices"][0].get("delta", {})
                        content_piece = delta.get("content", "")

                        # Skip empty or non-content chunks
                        if content_piece:
                            llm_answer += content_piece
                            live.update(llm_answer)
                            time.sleep(0.05)  # Smooth streaming effect

                except json.JSONDecodeError:
                    console.print("[bold red]⚠️ Warning: Received an invalid JSON response from LLM.[/bold red]")
                    continue  # Skip bad chunks

    return llm_answer


def highlight_code_blocks(text):
    code_block_pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
    parts = []
    last_end = 0

    for match in code_block_pattern.finditer(text):
        parts.append(text[last_end:match.start()])
        language = match.group(1) or "python"
        code = match.group(2)
        parts.append(Syntax(code, language, theme="monokai", line_numbers=False))
        last_end = match.end()

    parts.append(text[last_end:])
    return parts

def display_results(question, question_id, answers):
    console.print(Panel(f"[bold cyan]Question:[/bold cyan] {question}", expand=False))

    if question_id is None:
        console.print("[bold red]No relevant question found![/bold red]")
        return

    console.print(Panel(f"[bold magenta]Fetching top {len(answers)} answers from Stack Overflow...[/bold magenta]", expand=False))

    with Live("") as live:
        for i, (votes, stackoverflow_answer, raw_stackoverflow_answer) in enumerate(answers):
            panel_content = f"[bold yellow]Answer {i+1} (Votes: {votes}):[/bold yellow]\n"
            for part in highlight_code_blocks(stackoverflow_answer):
                panel_content += str(part) + "\n"
            live.update(panel_content)
            time.sleep(1)

    llm_answer = stream_llm_response(question, answers)

    console.print(Panel("[bold green]Final LLM Answer:[/bold green]", title="LLM Response", expand=False))
    for part in highlight_code_blocks(llm_answer):
        console.print(part)

    save_to_file(question, question_id, answers, llm_answer)

def save_to_file(question, question_id, answers, llm_answer):
    filename = "stackoverflow_responses.txt"
    with open(filename, "w", encoding="utf-8") as file:
        file.write(f"Question: {question}\n")
        file.write(f"Stack Overflow Question ID: {question_id}\n\n")

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
    question_id, answers = get_top_answers(question, num_answers=3)

    if not answers:
        console.print("[bold red]No answers found on Stack Overflow.[/bold red]")
    else:
        display_results(question, question_id, answers)
