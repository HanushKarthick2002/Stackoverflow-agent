let LLMFOUNDRY_TOKEN = null;

async function fetchLLMToken() {
    try {
        const response = await fetch("https://llmfoundry.straive.com/token", { credentials: "include" });
        if (!response.ok) {
            throw new Error(`Failed to fetch token: ${response.status}`);
        }
        const data = await response.json();
        LLMFOUNDRY_TOKEN = data.token;

    } catch (error) {
        console.error("Error fetching LLM token:", error);
        LLMFOUNDRY_TOKEN = null;
    }
}

// Fetch the token on page load
fetchLLMToken();

function showNotification(message, type = "info") {
    // Remove any existing alert
    const existingAlert = document.querySelector(".alert");
    if (existingAlert) {
        existingAlert.remove();
    }

    // Create a Bootstrap alert
    const notification = document.createElement("div");
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.role = "alert";
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    // Append the alert to the body or a specific container
    document.body.appendChild(notification);

    // Automatically remove the alert after 4 seconds
    setTimeout(() => {
        notification.remove();
    }, 4000);
}

function showLoginPopup() {
    // Remove any existing modal
    const existingModal = document.querySelector("#loginModal");
    if (existingModal) {
        existingModal.remove();
    }

    // Create a Bootstrap modal
    const modal = document.createElement("div");
    modal.id = "loginModal";
    modal.className = "modal fade";
    modal.tabIndex = "-1";
    modal.role = "dialog";
    modal.innerHTML = `
        <div class="modal-dialog" role="document">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Login Required</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <p>Please sign in to LLM Foundry first.</p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-primary" onclick="window.location.href='https://llmfoundry.straive.com/login'">Login</button>
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    `;

    // Append the modal to the body
    document.body.appendChild(modal);

    // Show the modal using Bootstrap's JavaScript API
    const bootstrapModal = new bootstrap.Modal(modal);
    bootstrapModal.show();
}

async function askQuestion() {
    const question = document.getElementById("questionInput").value.trim();
    const responseDiv = document.getElementById("llmOutput");
    const statusDiv = document.getElementById("status");

    if (!question) {
        showNotification("Please enter a question.", "warning");
        return;
    }

    if (!LLMFOUNDRY_TOKEN) {
        showLoginPopup();
        return;
    }

    responseDiv.innerHTML = "";
    statusDiv.innerText = "Fetching from Stack Overflow...";

    try {
        const stackOverflowAnswers = await fetchStackOverflowAnswers(question);
        
        if (!stackOverflowAnswers.length) {
            showNotification("⚠️ No relevant answers found on Stack Overflow.", "warning");
            return;
        }

        statusDiv.innerText = "Processing answers with LLM...";
        await fetchLLMResponse(question, stackOverflowAnswers);
    } catch (error) {
        showNotification("Error: Could not fetch response.", "error");
        console.error(error);
    }
}

async function fetchStackOverflowAnswers(question) {
    const searchUrl = `https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q=${encodeURIComponent(question)}&site=stackoverflow&accepted=True&filter=withbody`;
    
    try {
        const searchResponse = await fetch(searchUrl);
        const searchData = await searchResponse.json();

        if (!searchData.items || searchData.items.length === 0) {
            showNotification("No relevant solutions found on Stack Overflow.", "info");
            return [];
        }

        const questionIds = searchData.items.slice(0, 5).map(item => item.question_id);
        return await getTopAnswers(questionIds);
    } catch (error) {
        showNotification("Error fetching Stack Overflow questions.", "error");
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
            showNotification(`Error fetching answers for question ID ${qid}.`, "error");
        }
    }    
    return allAnswers.sort((a, b) => b.score - a.score).slice(0, 3);
}

// Define the asyncLLM function
async function* asyncLLM(apiUrl, options) {
    const response = await fetch(apiUrl, options);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let done = false;
    let buffer = ""; // Buffer to accumulate incomplete JSON chunks

    while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk; // Append the chunk to the buffer

        const lines = buffer.split("\n").filter(line => line.trim() !== "");
        buffer = ""; // Clear the buffer to process lines

        for (const line of lines) {
            if (line === "data: [DONE]") {
                // End of the stream, stop processing
                return;
            }

            if (line.startsWith("data: ")) {
                const jsonString = line.slice(6); // Remove the "data: " prefix
                try {
                    yield JSON.parse(jsonString);
                } catch (error) {
                    // If JSON parsing fails, re-add the line to the buffer for the next iteration
                    buffer += line + "\n";
                }
            }
        }
    }
}

async function fetchLLMResponse(question, answers) {
    const responseDiv = document.getElementById("llmOutput");
    const statusDiv = document.getElementById("status");
    
    statusDiv.innerText = "Generating final response...";
    responseDiv.innerHTML = "";

    const formattedAnswers = answers.map((ans, i) => 
        `🔹 <strong>Answer ${i + 1}</strong> (Votes: ${ans.score})<br>${ans.text}<br>`
    ).join("<br>");

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

    try {
        let currentChunk = "";

        for await (const data of asyncLLM("https://llmfoundry.straive.com/openai/v1/chat/completions", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${LLMFOUNDRY_TOKEN}:my-test-project`
            },
            credentials: "include",
            body: JSON.stringify(payload),
        })) {
            if (data.error) {
                console.error("API Error:", data.error);
                throw new Error(data.error.message || "LLM API Error");
            }

            if (data.choices && data.choices[0].delta.content) {
                const content = data.choices[0].delta.content;
                currentChunk += content;

                // Append content to the responseDiv
                responseDiv.innerHTML += content.replace(/\n/g, "<br>");
            }
        }

        statusDiv.innerText = "✅ Response received.";
    } catch (error) {
        showNotification("Error processing LLM response.", "error");
        console.error(error);
    }
}
