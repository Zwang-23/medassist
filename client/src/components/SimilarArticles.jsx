import React from 'react';
import { Paper, Typography, List, ListItem, ListItemText, Link } from '@mui/material';

const SimilarArticles = ({ articles }) => {
  if (!articles || articles.length === 0) return null;

  return (
    <Paper
      elevation={2} // Slightly less elevation than main Paper for hierarchy
      sx={{
        padding: '20px',
        borderRadius: '12px', // Matches chat window
        backgroundColor: '#ffffff', // White to match main content
        maxWidth: '1300px', 
        width: '100%',
        boxShadow: '0 4px 16px rgba(0, 0, 0, 0.1)', // Softer shadow
        mt: 2, // Space above to separate from other content
      }}
    >
      <Typography
        variant="h6"
        gutterBottom
        sx={{
          fontWeight: 600,
          color: '#1976d2', // Blue to match page headers
          marginBottom: '16px',
        }}
      >
        Similar Recent Articles
      </Typography>
      {articles.length > 0 ? (
        <List sx={{ padding: 0 }}>
          {articles.map((article, index) => (
            <ListItem
              key={index}
              disablePadding
              sx={{
                padding: '8px 0', // Vertical spacing between items
                borderBottom: index < articles.length - 1 ? '1px solid #eee' : 'none', // Subtle divider
                '&:hover': { backgroundColor: '#f5f5f5' }, // Hover effect
              }}
            >
              <ListItemText
                primary={
                  <Link
                    href={article.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    underline="hover"
                    sx={{
                      color: '#1976d2', // Blue for links
                      fontSize: '1rem',
                      fontWeight: 500,
                      '&:hover': { color: '#1565c0' }, // Darker blue on hover
                    }}
                  >
                    {article.title}
                  </Link>
                }
                secondary={
                  <Typography
                    variant="body2"
                    sx={{
                      color: '#666', // Gray to match other secondary text
                      marginTop: '4px',
                    }}
                  >
                    by {article.authors}
                  </Typography>
                }
              />
            </ListItem>
          ))}
        </List>
      ) : (
        <Typography variant="body2" sx={{ color: '#666', fontStyle: 'italic' }}>
          No similar articles found yet. Upload a PDF to see recommendations!
        </Typography>
      )}
    </Paper>
  );
};

export default SimilarArticles;