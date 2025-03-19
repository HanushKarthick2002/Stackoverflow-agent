import os
import sys
import requests
import warnings
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
import re

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

def format_answer_with_llm(question, answers):
    formatted_answers = "\n\n".join([f"Answer {i+1} (Votes: {votes}):\n{content}" for i, (votes, content, raw) in enumerate(answers)])

    llm_api_url = "https://llmfoundry.straive.com/openai/v1/chat/completions"
    llm_headers = {
        "Authorization": f"Bearer {os.environ['LLMFOUNDRY_TOKEN']}:my-test-project"
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
        ]
    }

    response = requests.post(llm_api_url, headers=llm_headers, json=llm_payload)

    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return f"Error: {response.status_code}, {response.text}"

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

def display_results(question, question_id, answers, llm_answer):
    console.print(Panel(f"[bold cyan]Question:[/bold cyan] {question}", expand=False))

    if question_id is None:
        console.print("[bold red]No relevant question found![/bold red]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Stack Overflow Question ID", justify="center")
    table.add_column("Votes", justify="center")

    table.add_row(str(question_id), "Top 3 Answers")
    console.print(table)

    for i, (votes, stackoverflow_answer, raw_stackoverflow_answer) in enumerate(answers):
        console.print(Panel(f"[bold yellow]Answer {i+1} (Votes: {votes}):[/bold yellow]", expand=False))
        for part in highlight_code_blocks(stackoverflow_answer):
            console.print(part)

    console.print(Panel("[bold green]LLM Simplified Answer:[/bold green]", title="LLM Response", expand=False))
    for part in highlight_code_blocks(llm_answer):
        console.print(part)

    save_to_file(question, question_id, answers, llm_answer)

def save_to_file(question, question_id, answers, llm_answer):
    filename = "llm_response.txt"
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
        llm_answer = format_answer_with_llm(question, answers)
        display_results(question, question_id, answers, llm_answer)
