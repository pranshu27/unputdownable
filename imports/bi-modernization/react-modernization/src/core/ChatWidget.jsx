import { useState } from "react";
import { MessageCircle, X, Send } from "lucide-react";
import "./ChatWidget.css";

const suggestedQuestions = [
  "What is this dashboard used for?",
  "How many data sources are there?",
  "What is the fact table?",
  "Show available KPIs",
  "Explain relationships"
];

const dummyResponses = {
  "what is this dashboard used for":
    "This dashboard helps analyze insurance premiums, policy performance, renewals, and customer profitability.",

  "how many data sources are there":
    "There are currently 7 data sources connected in this dashboard.",

  "what is the fact table":
    "The primary fact table is FCT_Insurance_Policy_Table.",

  "show available kpis":
    "Available KPIs include Total Premium, Premium Paid, Outstanding Premium, ROI, and Policy Renewal Rate.",

  "explain relationships":
    "There are 13 relationships connecting fact, dimension, and lookup tables."
};

const ChatWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");

  const [messages, setMessages] = useState([
    {
      type: "bot",
      text: "Hi 👋 I'm your Migration Assistant. Ask me about datasets, KPIs, lineage, relationships, or summary."
    }
  ]);

  const getBotResponse = (question) => {
    const lowerQuestion = question.toLowerCase();

    const matchedKey = Object.keys(dummyResponses).find((key) =>
      lowerQuestion.includes(key)
    );

    if (matchedKey) {
      return dummyResponses[matchedKey];
    }

    return "I couldn't find that information. Try asking about KPIs, sources, lineage, or relationships.";
  };

  const sendMessage = (question) => {
    const userText = question || input;

    if (!userText.trim()) return;

    const botResponse = getBotResponse(userText);

    setMessages((prev) => [
      ...prev,
      {
        type: "user",
        text: userText
      },
      {
        type: "bot",
        text: botResponse
      }
    ]);

    setInput("");
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="chat-fab"
      >
        {isOpen ? <X size={24} /> : <MessageCircle size={24} />}
      </button>

      {isOpen && (
        <div className="chat-window">
          <div className="chat-header">
            <span>Migration Assistant</span>
            <button onClick={() => setIsOpen(false)}>
              <X size={18} />
            </button>
          </div>


          <div className="chat-messages">
            {messages.map((msg, index) => (
              <div
                key={index}
                className={`chat-message ${msg.type}`}
              >
                {msg.text}
              </div>
            ))}
          </div>

          <div className="chat-suggestions">
            {suggestedQuestions.map((question) => (
              <button
                key={question}
                className="suggestion-chip"
                onClick={() => sendMessage(question)}
              >
                {question}
              </button>
            ))}
          </div>

          <div className="chat-input-container">
            <input
              type="text"
              placeholder="Ask about lineage, KPIs..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  sendMessage();
                }
              }}
            />

            <button onClick={() => sendMessage()}>
              <Send size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
};

export default ChatWidget;