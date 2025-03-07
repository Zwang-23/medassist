import React from 'react';
import { Container, Typography, Button, Box, Paper, Grid } from '@mui/material';
import { useNavigate } from 'react-router-dom';

const Home = () => {
  const navigate = useNavigate();

  const handleStartChat = () => {
    navigate('/chat');
  };

  return (
    <Container
      maxWidth={false}
      sx={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(135deg, #e3f2fd 0%, #f5f5f5 100%)', // Subtle gradient background
        padding: '40px',
      }}
    >
      <Paper
        elevation={6}
        sx={{
          padding: { xs: '20px', md: '40px' }, // Responsive padding
          borderRadius: '20px',
          backgroundColor: '#ffffff',
          maxWidth: '1100px',
          width: '100%',
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.1)', // Softer shadow
        }}
      >
        <Grid container spacing={4} alignItems="center">
          {/* Text Section */}
          <Grid item xs={12} md={6}>
            <Typography
              variant="h3"
              gutterBottom
              sx={{
                fontWeight: 700,
                color: '#1976d2', // Professional blue
                lineHeight: 1.2,
              }}
            >
              Intelligent Medical Research Assistant
            </Typography>
            <Typography
              variant="h5"
              gutterBottom
              sx={{
                color: '#555',
                fontWeight: 500,
                marginBottom: '20px',
              }}
            >
              Your Partner in Medical Research
            </Typography>
            <Typography
              variant="body1"
              sx={{
                color: '#666',
                fontSize: '1.1rem',
                lineHeight: 1.6,
                marginBottom: '30px',
              }}
            >
              MedAI Assistant empowers researchers by analyzing medical PDFs and providing insightful answers. Upload your documents and unlock a world of knowledge today.
            </Typography>
            <Button
              variant="contained"
              onClick={handleStartChat}
              sx={{
                backgroundColor: '#1976d2', // Matches title color
                '&:hover': { backgroundColor: '#1565c0' },
                padding: '12px 32px',
                fontSize: '1rem',
                fontWeight: 600,
                borderRadius: '8px',
                textTransform: 'none', // Avoid all-caps for a friendlier look
                boxShadow: '0 4px 12px rgba(25, 118, 210, 0.3)',
              }}
            >
              Start Exploring Now
            </Button>
          </Grid>

          {/* Image Section */}
          <Grid item xs={12} md={6}>
            <Box
              sx={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
              }}
            >
              <img
                src="/icons/chatbot.jpg" // Keep your image or update to a more thematic one
                alt="MedAI Assistant"
                style={{
                  width: '100%',
                  maxWidth: '400px', // Cap size for consistency
                  height: 'auto',
                  borderRadius: '12px',
                  boxShadow: '0 4px 16px rgba(0, 0, 0, 0.1)', // Subtle shadow
                }}
              />
            </Box>
          </Grid>
        </Grid>
      </Paper>
    </Container>
  );
};

export default Home;