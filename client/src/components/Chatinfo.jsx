import React, { useState } from 'react';
import { Box, Typography, Paper, List, ListItem, ListItemText, Button, Collapse } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';

const ChatInfo = () => {
  const [isExpanded, setIsExpanded] = useState(true); // Default to expanded

  const handleToggle = () => {
    setIsExpanded((prev) => !prev); // Toggle state
  };

  return (
    <Box sx={{ maxWidth: '1300px', width: '100%', margin: '0 auto', padding: { xs: '10px', md: '20px' } }}>
      <Paper
        elevation={2}
        sx={{
          padding: '20px',
          borderRadius: '12px', // Matches chat window
          backgroundColor: '#ffffff', // White to match main content
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.1)', // Softer shadow
          width: '100%',
        }}
      >
        {/* Header with Toggle Button */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography
            variant="h5"
            sx={{
              fontWeight: 700,
              color: '#1976d2', // Blue to match page
            }}
          >
            Meet Your Intelligent Medical Research Assistant
          </Typography>
          <Button
            variant="outlined"
            onClick={handleToggle}
            endIcon={isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            sx={{
              color: '#1976d2',
              borderColor: '#1976d2',
              borderRadius: '8px',
              textTransform: 'none',
              '&:hover': { borderColor: '#1565c0', color: '#1565c0' },
            }}
          >
            {isExpanded ? 'Minimize' : 'Expand'}
          </Button>
        </Box>

        {/* Collapsible Content */}
        <Collapse in={isExpanded}>
          {/* Introduction */}
          <Typography
            variant="body1"
            paragraph
            sx={{
              color: '#666',
              lineHeight: 1.6,
            }}
          >
            Welcome to the Intelligent Medical Research Assistant! I’m here to help you explore medical PDFs with ease.
            Upload a document, ask questions, and get precise answers powered by advanced AI. Whether you’re researching
            treatments or analyzing studies, I’ve got you covered. Let’s get started!
          </Typography>

          {/* Instruction Video */}
          <Box sx={{ mb: 3 }}>
            <Typography
              variant="h6"
              gutterBottom
              sx={{
                fontWeight: 600,
                color: '#1976d2',
              }}
            >
              Watch the Instruction Video
            </Typography>
            <video
              width="100%"
              controls
              style={{ maxWidth: '600px', borderRadius: '8px' }}
            >
              <source src="video/Demo.mp4" type="video/mp4" />
              Your browser does not support the video tag.
            </video>
          </Box>

          {/* User Guide */}
          <Typography
            variant="h6"
            gutterBottom
            sx={{
              fontWeight: 600,
              color: '#1976d2',
              mt: 2,
            }}
          >
            How to Use Me
          </Typography>
          <List sx={{ padding: 0 }}>
            <ListItem sx={{ alignItems: 'flex-start', padding: '8px 0' }}>
              <ListItemText
                primary={<Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#555' }}>Choose File Button</Typography>}
                secondary={
                  <Typography variant="body2" sx={{ color: '#666' }}>
                    Opens your file explorer to select a PDF. Pick a medical document you want me to analyze.
                  </Typography>
                }
              />
            </ListItem>
            <ListItem sx={{ alignItems: 'flex-start', padding: '8px 0' }}>
              <ListItemText
                primary={<Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#555' }}>Upload PDF Button</Typography>}
                secondary={
                  <Typography variant="body2" sx={{ color: '#666' }}>
                    Sends your selected PDF to me for processing. Once uploaded, I’ll use it to find similar articles and answer your questions.
                    If you upload another file, I’ll switch to the most recent one.
                  </Typography>
                }
              />
            </ListItem>
            <ListItem sx={{ alignItems: 'flex-start', padding: '8px 0' }}>
              <ListItemText
                primary={<Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#555' }}>Voice Mode Button</Typography>}
                secondary={
                  <Typography variant="body2" sx={{ color: '#666' }}>
                    Activate voice mode to interact using your voice. Select a language to match your speech.
                  </Typography>
                }
              />
            </ListItem>
            <ListItem sx={{ alignItems: 'flex-start', padding: '8px 0' }}>
              <ListItemText
                primary={<Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#555' }}>Send Button</Typography>}
                secondary={
                  <Typography variant="body2" sx={{ color: '#666' }}>
                    Type a question about your PDF in the text box and click Send—or press Enter—to get my answer.
                  </Typography>
                }
              />
            </ListItem>
            <ListItem sx={{ alignItems: 'flex-start', padding: '8px 0' }}>
              <ListItemText
                primary={<Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#555' }}>Reset Button</Typography>}
                secondary={
                  <Typography variant="body2" sx={{ color: '#666' }}>
                    Clears the current session, removing all chat history, uploaded files, and similar articles. Use this to start over with a new PDF.
                  </Typography>
                }
              />
            </ListItem>
            <ListItem sx={{ alignItems: 'flex-start', padding: '8px 0' }}>
              <ListItemText
                primary={<Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#555' }}>Similar Articles Section</Typography>}
                secondary={
                  <Typography variant="body2" sx={{ color: '#666' }}>
                    After uploading a PDF, I’ll search for up to 5 related articles from Semantic Scholar and PubMed, excluding the uploaded paper.
                    Click the article titles to explore them in a new tab.
                  </Typography>
                }
              />
            </ListItem>
          </List>
        </Collapse>
      </Paper>
    </Box>
  );
};

export default ChatInfo;