let LLMFOUNDRY_TOKEN = null;

async function fetchLLMToken() {
    try {
        const response = await fetch("https://llmfoundry.straive.com/token", { credentials: "include" });
        const data = await response.json();
        LLMFOUNDRY_TOKEN = data.token;
    } catch (error) {
        console.error("Error fetching LLM token:", error);
        LLMFOUNDRY_TOKEN = null;
    }
}

// Fetch the token on page load
fetchLLMToken();


async function askQuestion() {
    const question = document.getElementById("questionInput").value.trim();
    const responseDiv = document.getElementById("llmOutput");
    const statusDiv = document.getElementById("status");

    if (!question) {
        alert("Please enter a question.");
        return;
    }

    if (!LLMFOUNDRY_TOKEN) {
        alert("Please sign in to LLM Foundry first.");
        return;
    }

    responseDiv.innerHTML = "";
    statusDiv.innerText = "Fetching from Stack Overflow...";

    try {
        const stackOverflowAnswers = await fetchStackOverflowAnswers(question);
        
        if (!stackOverflowAnswers.length) {
            responseDiv.innerHTML = "⚠️ No relevant answers found on Stack Overflow.";
            return;
        }

        statusDiv.innerText = "Processing answers with LLM...";
        await fetchLLMResponse(question, stackOverflowAnswers);
    } catch (error) {
        responseDiv.innerHTML = "⚠️ Error: Could not fetch response.";
        console.error(error);
    }
}
async function fetchStackOverflowAnswers(question) {
    const searchUrl = `https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q=${encodeURIComponent(question)}&site=stackoverflow&accepted=True&filter=withbody`;
    
    try {
        const searchResponse = await fetch(searchUrl);
        const searchData = await searchResponse.json();

        if (!searchData.items || searchData.items.length === 0) {
            console.log("No relevant solutions found on Stack Overflow.");
            return [];
        }

        const questionIds = searchData.items.slice(0, 5).map(item => item.question_id);
        return await getTopAnswers(questionIds);
    } catch (error) {
        console.error("Error fetching Stack Overflow questions:", error);
        return [];
    }
}

async function getTopAnswers(questionIds) {
    let allAnswers = [];

    for (const qid of questionIds) {
        const url = `https://api.stackexchange.com/2.3/questions/${qid}/answers?order=desc&sort=votes&site=stackoverflow&filter=withbody`;
        
        try {
            const response = await fetch(url);
            const data = await response.json();

            if (data.items && data.items.length > 0) {
                for (let answer of data.items.slice(0, 3)) {
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(answer.body, "text/html");
                    const cleanedText = doc.body.textContent || "";

                    allAnswers.push({ score: answer.score, text: cleanedText });
                }
            }
        } catch (error) {
            console.error(`Error fetching answers for question ID ${qid}:`, error);
        }
    }
    
    // Sort all answers by score in descending order and return the top 3
    return allAnswers.sort((a, b) => b.score - a.score).slice(0, 3);
}


async function fetchLLMResponse(question, answers) {
    const responseDiv = document.getElementById("llmOutput");
    const statusDiv = document.getElementById("status");
    
    statusDiv.innerText = "Generating final response...";
    responseDiv.innerHTML = ""; // Clear previous response

    const formattedAnswers = answers.map((ans, i) => 
        `🔹 **Answer ${i + 1}** (Votes: ${ans.score})\n${ans.text}\n`
    ).join("\n");

    const payload = {
        model: "gpt-4o-mini",
        messages: [
            {
                role: "user",
                content: `You are an expert in simplifying technical content while maintaining accuracy. Given a technical question and several extracted answers from Stack Overflow, your task is to combine and present them in a clear, easy-to-understand manner without altering their core meaning.

                Instructions:
                - Summarize key insights from all answers into a single, well-structured response.
                - Ensure clarity by avoiding unnecessary jargon while preserving technical accuracy.
                - If the answers contain code, format it neatly and add brief explanations if needed.
                - If multiple solutions exist, present them logically and indicate any differences or trade-offs.
                - Keep the response concise but informative, ensuring completeness.
                
                **Input:**  
                Question: ${question}  
                Extracted Answers:  
                ${formattedAnswers}`
                
            }
        ],
        stream: true
    };

    const response = await fetch("https://llmfoundry.straive.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${LLMFOUNDRY_TOKEN}:my-test-project` },
        credentials: "include",
        body: JSON.stringify(payload)
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        buffer += chunk;

        const dataLines = buffer.split("\n");
        buffer = dataLines.pop(); 

        for (let line of dataLines) {
            line = line.trim();
            if (!line || line === "data: [DONE]") continue;

            if (line.startsWith("data: ")) {
                const jsonStr = line.slice(6).trim();

                try {
                    const jsonChunk = JSON.parse(jsonStr);
                    const contentPiece = jsonChunk.choices?.[0]?.delta?.content || "";

                    if (contentPiece) {
                        responseDiv.innerHTML += contentPiece.replace(/\n/g, "<br>"); // Ensures line breaks
                    }
                } catch (error) {
                    console.error("Error processing LLM stream:", error, "Raw data:", jsonStr);
                }
            }
        }
    }

    statusDiv.innerText = "✅ Response received.";
}
