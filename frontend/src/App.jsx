// frontend/src/App.jsx

import React, { useState } from 'react';
import axios from 'axios';

import "@chatscope/chat-ui-kit-styles/dist/default/styles.min.css";
import {
  MainContainer,
  ChatContainer,
  MessageList,
  Message,
  MessageInput,
  TypingIndicator,
} from "@chatscope/chat-ui-kit-react";

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const useChat = () => {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Bonjour ! Comment puis-je vous aider aujourd\'hui ?' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = async (newInput) => {
    const textToSend = newInput || input;
    if (!textToSend.trim() || isLoading) return;

    const userMessage = { role: 'user', content: textToSend };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInput('');
    setIsLoading(true);

    try {
      const { data } = await axios.post(`${API_URL}/chat`, { messages: newMessages });
      setMessages(data.messages);
    } catch (error) {
      console.error("Erreur lors de la communication avec l'API:", error);
      setMessages(prev => [...prev, { role: 'assistant', content: "Désolé, une erreur est survenue." }]);
    } finally {
      setIsLoading(false);
    }
  };

  return { messages, input, setInput, isLoading, sendMessage };
};


export default function App() {
  const { messages, input, setInput, isLoading, sendMessage } = useChat();

  return (
    <div style={{ position: 'relative', height: '100vh', maxWidth: '700px', margin: '0 auto' }}>
      <MainContainer>
        <ChatContainer>
          <MessageList
            typingIndicator={isLoading ? <TypingIndicator content="Le canard réfléchit..." /> : null}
          >
            {messages.map((msg, idx) => {
              const messageModel = {
                message: msg.content,
                direction: msg.role === 'user' ? 'outgoing' : 'incoming',
                sender: msg.role,
                position: 'single'
              };
              return <Message key={idx} model={messageModel} />;
            })}
          </MessageList>
          
          <MessageInput
            placeholder="Posez votre question…"
            value={input}
            onChange={(val) => setInput(val)}
            onSend={(innerHtml, textContent) => sendMessage(textContent)}
            disabled={isLoading}
            attachButton={false}
          />
        </ChatContainer>
      </MainContainer>
    </div>
  );
}