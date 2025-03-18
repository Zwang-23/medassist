import React, { useState, useEffect, useRef } from 'react';
import { TextField, Button, Container, Box, Grid, Typography, Paper, CircularProgress, LinearProgress, IconButton} from '@mui/material';
import axios from 'axios';


import ReactMarkdown from 'react-markdown';
import ChatInfo from './Chatinfo';
import { Select, MenuItem } from '@mui/material';
import SimilarArticles from './SimilarArticles';


const GlobalStyles = () => (
  <style>{`
    @keyframes fadeIn {
      from {
        opacity: 0;
      }
      to {
        opacity: 1;
      }
    }
  `}</style>
);

const Chat = () => {
  const [message, setMessage] = useState('');
  const [chatHistory, setChatHistory] = useState([{
    role: 'assistant',
    content: "Hello! I'm your Intelligent Medical Research Assistant. I can help you analyze medical PDFs by answering questions based on their content. Upload a PDF to get started!"
  }]);
  const [file, setFile] = useState(null);
  const chatContainerRef = useRef(null);
  const fileInputRef = useRef(null);
  const [isListening, setIsListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState('');
  const [voiceMode, setVoiceMode] = useState(false);
  const [isResponding, setIsResponding] = useState(false);
  const [recognition, setRecognition] = useState(null);
  const RESTART_DELAY = 0;
  const [keywords, setKeywords] = useState([]);
  const [similarArticles, setSimilarArticles] = useState([]);
  const [selectedLanguage, setSelectedLanguage] = useState(''); // Empty string means browser default
  const [isStreaming, setIsStreaming] = useState(false);

  const [uploadedFileName, setUploadedFileName] = useState(null); 
  

  useEffect(() => {
    const resetSession = async () => {
      try {
        await axios.post('/api/reset', {}, { withCredentials: true });
        console.log('Session reset on page load');
      } catch (error) {
        console.error('Error resetting session:', error);
      }
    };
    resetSession();
  }, []);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatHistory]);


  const [isUploading, setIsUploading] = useState(false);
  
  const searchSimilarArticles = async (query) => {
    const searchUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${encodeURIComponent(query)}&retmode=json&retmax=5&sort=date`;
    try {
      const response = await fetch(searchUrl);
      const data = await response.json();
      const pmids = data.esearchresult.idlist || [];
      if (pmids.length === 0) return [];

      const detailsUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=${pmids.join(',')}&retmode=json`;
      const detailsResponse = await fetch(detailsUrl);
      const detailsData = await detailsResponse.json();

      return pmids.map(pmid => {
        const article = detailsData.result[pmid];
        return {
          title: article.title,
          authors: article.authors.map(author => author.name).join(', '),
          link: `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`
        };
      });
    } catch (error) {
      console.error('Error fetching similar articles:', error);
      setChatHistory(prev => [...prev, { role: 'assistant', content: 'Error finding similar articles.' }]);
      return [];
    }
  };
  const handleFileUpload = async () => {
    if (!file) {
      setChatHistory([...chatHistory, { role: 'assistant', content: 'Please select a file first.' }]);
      return;
    }
    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      console.log('Uploading file:', file.name);
      const response = await axios.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        withCredentials: true,
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(percentCompleted);} // Update progress state
      });
      console.log('Upload response:', response.data);
      setChatHistory([...chatHistory, { role: 'assistant', content: response.data.response }]);
      setFile(null);
      setUploadedFileName(file.name);
      setUploadProgress(0);
      setKeywords(response.data.keywords || []);
      setSimilarArticles(response.data.similar_articles || []);
      console.log('Keywords set to:', response.data.keywords);
      console.log('Similar articles set to:', response.data.similar_articles);
    } catch (error) {
      console.error('Upload error:', error.response ? error.response.data : error.message);
      const errorMessage = error.response?.data?.error || 'Error uploading file';
      setChatHistory([...chatHistory, { role: 'assistant', content: errorMessage }]);
    } finally {
      setIsUploading(false); // End uploading
    }
  };
  const [uploadProgress, setUploadProgress] = useState(0);
  
  useEffect(() => {
    let recognitionInstance;
    let restartTimer;
  
    const initializeVoiceMode = () => {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      
      if (!SpeechRecognition) {
        console.error('Speech recognition not supported');
        return null;
      }
  
      const newRecognition = new SpeechRecognition();
      newRecognition.continuous = true;
      newRecognition.interimResults = true;
      if (selectedLanguage) {
        newRecognition.lang = selectedLanguage; // Set language if specified
        console.log('Recognition language set to:', selectedLanguage);
      } else {
        console.log('No language specified, using browser default');
      }
    
  
      newRecognition.onresult = (event) => {
        if (isResponding) return;
        const results = event.results[event.results.length - 1];
        const transcript = results[0].transcript;
        if (results.isFinal) {
          handleSendMessage(transcript.trim());
          setInterimTranscript('');
        } else {
          setInterimTranscript(transcript);
        }
      };
  
      newRecognition.onerror = (event) => {
        console.log('Recognition error:', event.error);
        setIsListening(false);
        if (event.error === 'no-speech') {
          console.log('No speech detected - waiting longer');
          // Ignore no-speech errors
          return;
        }
        setIsListening(false);
        if (voiceMode) {
          restartTimer = setTimeout(() => {
            if (voiceMode && recognitionInstance) {
              console.log('Restarting after error');
              recognitionInstance.start();
            }
          }, RESTART_DELAY);
        }
      };
  
      newRecognition.onend = () => {
        console.log('Recognition ended');
        setIsListening(false);
        if (voiceMode && !isResponding) {
          console.log('Restarting voice mode');
          restartTimer = setTimeout(() => {
            if (voiceMode && recognitionInstance) {
              try {
                console.log('Attempting restart');
                recognitionInstance.start();
                setIsListening(true);
              } catch (error) {
                console.error('Restart error:', error);
                }
              }
          }, RESTART_DELAY); // Increased delay to 1 second
        }
      };
  
      return newRecognition;
    };
  
    if (voiceMode) {
      recognitionInstance = initializeVoiceMode();
      setRecognition(recognitionInstance);
  
      // Start recognition
      try {
        recognitionInstance.start();
        setIsListening(true);
        console.log('Recognition initialized');
      } catch (error) {
        console.error('Error starting recognition:', error);
      }
  
      // Add cleanup
      return () => {
        console.log('Cleaning up voice mode');
        clearTimeout(restartTimer);
        if (recognitionInstance) {
          recognitionInstance.stop();
          recognitionInstance.onend = null; // Remove event handler
          recognitionInstance.onerror = null;
        }
      };
    }
  }, [voiceMode, isResponding, selectedLanguage]); // Only rerun when voiceMode changes
  
  // Update the voice mode toggle handler
  const toggleVoiceMode = () => {
    if (voiceMode) {
      console.log('Disabling voice mode');
      // Disable voice mode
      setVoiceMode(false);
      setIsListening(false);
      if (recognition) {
        recognition.stop();
        recognition.onend = null; // Prevent automatic restart
        recognition.onerror = null;
      }
      setIsListening(false);
    } else {
      console.log('Enabling voice mode');
      // Enable voice mode
      setVoiceMode(true);
    }
  };

  const handleSendMessage = async (text = message) => {
    let messageText = '';
  
    // If input is an event object, use message state
    if (text && typeof text === 'object' && text.preventDefault) {
      messageText = message;
    } else {
      // Otherwise use the provided text or fall back to message state
      messageText = text || message;
    }
    
    // Convert to string and check if empty (without using trim)
    messageText = String(messageText);
    if (!messageText || messageText.length === 0) return;
    setMessage(''); // Clear the input field
  
    setChatHistory(prev => [...prev, { role: 'user', content: text }]);
    setIsStreaming(false); 
    setIsResponding(true);
    try {
      
  
      const response = await fetch(`/api/stream?message=${encodeURIComponent(text)}`, {
        credentials: 'include',
      });
      if (!response.body) {
        throw new Error('No response body');
      }
  
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullResponse = '';
      const processStream = async () => {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          const chunk = decoder.decode(value);
          const lines = chunk.split('\n\n');
          
          lines.forEach(line => {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === 'stream') {
                  if (!isStreaming) setIsStreaming(true);
                  fullResponse += data.content;
                  setChatHistory(prev => {
                    const last = prev[prev.length - 1];
                    return last.role === 'assistant' 
                      ? [...prev.slice(0, -1), { role: 'assistant', content: fullResponse }]
                      : [...prev, { role: 'assistant', content: fullResponse }];
                  });
                }
              } catch (error) {
                console.error('JSON parse error:', error);
              }
            }
          });
        }
      };
  
      await processStream();
    } catch (error) {
      console.error('Message error:', error);
      setChatHistory(prev => [...prev, { role: 'assistant', content: 'Error sending message' }]);
    } finally {
      setIsResponding(false);
      // Removed: restart recognition
    }
  };


  const handleResetSession = async () => {
    try {
      await axios.post('/api/reset', {}, { withCredentials: true });
      // Reset frontend state
      setChatHistory([
        {
          role: 'assistant',
          content: "Session reset successfully! I'm your Intelligent Medical Research Assistant. Upload a PDF to get started!"
        }
      ]);
      setMessage('');
      setFile(null);
      setUploadedFileName(null);
      setUploadProgress(0);
      if (fileInputRef.current) {
        fileInputRef.current.value = ''; // Reset the file input field
      }
      console.log('Session reset by user');
    } catch (error) {
      console.error('Error resetting session:', error);
      setChatHistory([...chatHistory, { role: 'assistant', content: 'Error resetting session. Please try again.' }]);
    }
  };

  return (
    <Container
      maxWidth={false}
      sx={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(135deg, #e3f2fd 0%, #f5f5f5 100%)',
        padding: { xs: '20px', md: '40px' },
      }}
    >
      <GlobalStyles />
      <Paper
        elevation={6}
        sx={{
          padding: { xs: '20px', md: '40px' },
          borderRadius: '20px',
          backgroundColor: '#ffffff',
          maxWidth: '1300px',
          width: '100%',
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.1)',
        }}
      >
        <Grid container spacing={3}>
          {/* Header */}
          <Grid item xs={12}>
            <Typography
              variant="h4"
              textAlign="center"
              sx={{
                fontWeight: 700,
                color: '#1976d2',
                marginBottom: '20px',
              }}
            >
              Intelligent Medical Research Assistant
            </Typography>
            <Box sx={{ maxWidth: '1300px', margin: '0 auto 20px' }}>
              <ChatInfo />
            </Box>
          </Grid>

          {/* Chat Window */}
          <Grid item xs={12}>
            <Paper
              elevation={2}
              sx={{
                padding: '20px',
                height: '600px',
                overflowY: 'auto',
                borderRadius: '12px',
                backgroundColor: '#fafafa',
              }}
              ref={chatContainerRef}
            >
              {chatHistory.map((msg, index) => (
                <Box
                  key={index}
                  mb={2}
                  sx={{
                    textAlign: msg.role === 'user' ? 'right' : 'left',
                    animation: 'fadeIn 0.5s ease-in',
                  }}
                >
                  <Box
                    sx={{
                      display: 'inline-block',
                      backgroundColor: msg.role === 'user' ? '#e3f2fd' : '#e8f5e9',
                      borderRadius: '12px',
                      padding: '12px 16px',
                      maxWidth: '70%',
                      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
                    }}
                  >
                    <Box display="flex" alignItems="center" sx={{ mb: 1 }}>
                      <Box
                        component="img"
                        src={msg.role === 'user' ? '/icons/user.png' : '/icons/chatbot.jpg'}
                        alt={msg.role}
                        sx={{ width: 36, height: 36, mr: 1, borderRadius: '50%' }}
                      />
                      <Typography sx={{ fontWeight: 600, color: '#666', fontSize: '20px' }}>
                        {msg.role === 'user' ? 'You' : 'Assistant'}
                      </Typography>
                    </Box>
                    <ReactMarkdown
                      components={{
                        p: ({ children }) => <Typography sx={{ color: '#666', mb: 0, fontSize: '16px'}}>{children}</Typography>,
                        ul: ({ children }) => <ul style={{ paddingLeft: '20px', margin: 0 }}>{children}</ul>,
                        li: ({ children }) => <li style={{ marginBottom: '6px' }}>{children}</li>,
                        strong: ({ children }) => <strong>{children}</strong>,
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </Box>
                </Box>
              ))}
              {isResponding && !isStreaming && (
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 2 }}>
                  <CircularProgress size={30} sx={{ color: '#1976d2' }} />
                  <Typography variant="body2" sx={{ ml: 2, color: '#666' }}>Thinking...</Typography>
                </Box>
              )}
              {voiceMode && (
                <Box
                  sx={{
                    textAlign: 'center',
                    color: '#666',
                    fontStyle: 'italic',
                    bgcolor: '#f5f5f5',
                    borderRadius: '8px',
                    padding: '8px',
                    mt: 2,
                  }}
                >
                  🎤 Listening: {interimTranscript}
                </Box>
              )}
            </Paper>
          </Grid>

          {/* Input and Controls */}
          <Grid item xs={12}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {/* Text Input */}
              <Box display="flex" alignItems="center" gap={2}>
                <TextField
                  fullWidth
                  variant="outlined"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                  placeholder="Type your message..."
                  multiline
                  minRows={1}
                  maxRows={5}
                  sx={{
                    maxWidth: '900px',
                    '& .MuiOutlinedInput-root': {
                      borderRadius: '8px',
                      bgcolor: '#fff',
                    },
                  }}
                />
                <Button
                  variant="contained"
                  onClick={() => handleSendMessage(message)}
                  sx={{
                    bgcolor: '#1976d2',
                    '&:hover': { bgcolor: '#1565c0' },
                    padding: '10px 20px',
                    borderRadius: '8px',
                  }}
                >
                  Send
                </Button>
                <Button
                  variant="contained"
                  onClick={handleResetSession}
                  sx={{
                    bgcolor: '#f44336',
                    '&:hover': { bgcolor: '#d32f2f' },
                    padding: '10px 20px',
                    borderRadius: '8px',
                  }}
                >
                  Reset
                </Button>
              </Box>

              {/* File Upload and Voice Controls */}
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <Box
                  sx={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: 2,
                  }}
                >
                  {/* Left: File Controls */}
                  <Box display="flex" alignItems="center" gap={1}>
                    <Button
                      variant="contained"
                      component="label"
                      sx={{ bgcolor: '#4caf50', '&:hover': { bgcolor: '#45a049' }, borderRadius: '8px' }}
                    >
                      Choose File
                      <input
                        type="file"
                        accept=".pdf"
                        hidden
                        onChange={(e) => setFile(e.target.files?.[0] || null)}
                      />
                    </Button>
                    <Button
                      variant="contained"
                      onClick={handleFileUpload}
                      disabled={!file || isUploading}
                      startIcon={isUploading ? <CircularProgress size={20} color="inherit" /> : null}
                      sx={{ bgcolor: '#1976d2', '&:hover': { bgcolor: '#1565c0' }, borderRadius: '8px' }}
                    >
                      {isUploading ? 'Uploading...' : 'Upload PDF'}
                    </Button>
                  </Box>

                  {/* Right: Voice Controls */}
                  <Box display="flex" alignItems="center" gap={2}>
                    <Button
                      variant="contained"
                      onClick={toggleVoiceMode}
                      sx={{
                        bgcolor: voiceMode ? '#f44336' : '#1976d2',
                        '&:hover': { bgcolor: voiceMode ? '#d32f2f' : '#1565c0' },
                        borderRadius: '8px',
                      }}
                    >
                      {voiceMode ? 'Stop Listening' : 'Voice Mode'}
                    </Button>
                    <Select
                      value={selectedLanguage}
                      onChange={(e) => setSelectedLanguage(e.target.value)}
                      displayEmpty
                      sx={{ minWidth: '150px', borderRadius: '8px' }}
                    >
                      <MenuItem value="">Select Language</MenuItem>
                      <MenuItem value="en-US">English</MenuItem>
                      <MenuItem value="es-ES">Español</MenuItem>
                      <MenuItem value="fr-FR">Français</MenuItem>
                      <MenuItem value="zh-CN">中文</MenuItem>
                      <MenuItem value="ar">العربية</MenuItem>
                    </Select>
                  </Box>
                </Box>

                {/* File Name Display */}
                {(file || uploadedFileName) && !isUploading && (
                  <Box sx={{ textAlign: 'left' }}>
                    {file && <Typography variant="body2" sx={{ color: '#666' }}>Selected: {file.name}</Typography>}
                    {uploadedFileName && !file && (
                      <Typography variant="body2" sx={{ color: '#666' }}>
                        Current: {uploadedFileName}
                      </Typography>
                    )}
                  </Box>
                )}
              </Box>

              {/* Upload Progress */}
              {isUploading && (
                <Box sx={{ maxWidth: '600px', mx: 'auto', mt: 2 }}>
                  <LinearProgress variant="determinate" value={uploadProgress} sx={{ borderRadius: '4px' }} />
                  <Typography variant="caption" sx={{ textAlign: 'center', display: 'block', mt: 1, color: '#666' }}>
                    Uploading... {uploadProgress}%
                  </Typography>
                </Box>
              )}

              {/* Keywords and Similar Articles */}
              {keywords.length > 0 && (
                <Box mt={2}>
                  <Typography variant="body1" sx={{ color: '#666' }}>
                    Keywords: {keywords.join(', ')}
                  </Typography>
                </Box>
              )}
              <SimilarArticles articles={similarArticles} />
            </Box>
          </Grid>
        </Grid>
      </Paper>
    </Container>
  );
};

export default Chat;