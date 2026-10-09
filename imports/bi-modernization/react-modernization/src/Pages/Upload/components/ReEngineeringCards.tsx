import React from 'react';
import { Box, Card, CardContent, Typography, Button } from '@mui/material';
import StorageIcon from '@mui/icons-material/Storage';
import BarChartIcon from '@mui/icons-material/BarChart';
import LayersIcon from '@mui/icons-material/Layers';
import './ReEngineeringCards.scss';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { useNavigate } from "react-router-dom";
import XIcon from '../../../Assets/Xicon.tsx';
type WorkflowType = 'data' | 'sttm' | 'migration';

interface ReEngineeringCardsProps {
    onSelectWorkflow: (workflow: WorkflowType) => void;
}

const ReEngineeringCards: React.FC<ReEngineeringCardsProps> = ({ onSelectWorkflow }) => {
    const cards = [
        // {
        //     id: 'data' as WorkflowType,
        //     title: 'Data Engineering Agent',
        //     description:
        //         'Generate production-ready data pipelines from BRD or Jira stories and deploy seamlessly on Databricks.',
        //     icon: <StorageIcon sx={{ fontSize: '40px !important' }} />,
        //     gradient: 'linear-gradient(135deg, #2C3E50 0%, #34495E 100%)',
        //     bgPattern:
        //         'radial-gradient(circle at 20% 80%, rgba(255,255,255,0.1) 0%, transparent 50%)'
        // },
        // {
        //     id: 'sttm' as WorkflowType,
        //     title: 'STTM Agent',
        //     description:
        //         'Automatically generate source-to-target mappings from business documents and metadata inputs.',
        //     icon: <BarChartIcon sx={{ fontSize: '40px !important' }} />,
        //     gradient: 'linear-gradient(135deg, #2563EB 0%, #3B82F6 100%)',
        //     bgPattern:
        //         'radial-gradient(circle at 80% 20%, rgba(255,255,255,0.15) 0%, transparent 50%)'
        // },
        {
            id: 'migration' as WorkflowType,
            title: 'Migration Agent',
            description:
                'Accelerate legacy system modernization and migrate workloads to Databricks with automated transformation support.',
            icon: <LayersIcon sx={{ fontSize: '40px !important' }} />,
            gradient: 'linear-gradient(135deg, #8B5CF6 0%, #A78BFA 100%)',
            bgPattern:
                'radial-gradient(circle at 50% 50%, rgba(255,255,255,0.12) 0%, transparent 60%)'
        }
    ];

    const navigate = useNavigate();
    const handleBackToSelection = () => {
        navigate('/');
    }

    return (
        <Box className="reengineering-cards-container">
            <Box
                sx={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",           // tighter gap
                    mb: 5,
                }}
            >
                <Box
                    sx={{
                        display: "flex",
                        alignItems: "center",
                        lineHeight: 0,      // remove extra space under icon
                    }}
                >
                    <XIcon size={58} />
                </Box>

                <Typography
                    sx={{
                        background: "linear-gradient(90deg, #003087 0%, #C5162D 100%)",
                        WebkitBackgroundClip: "text",
                        WebkitTextFillColor: "transparent",
                        fontWeight: 900,
                        fontSize: "48px !important",
                        letterSpacing: "-1px",
                        lineHeight: 1,      // important for vertical alignment
                        mb: 0,              // remove extra bottom space
                        display: "flex",
                        alignItems: "center",
                    }}
                >
                    Companion
                </Typography>
            </Box>


            {/* <Box className="cards-grid"> */}
            <Box className="cards-grid" sx={{ display: 'flex', justifyContent: 'center' }}>
                {cards.map((card) => (
                    <Card
                        key={card.id}
                        className="reengineering-card"
                        onClick={() => {
                            localStorage.setItem("selectedWorkflow", card.id);
                            onSelectWorkflow(card.id)
                        }}
                        sx={{
                            background: card.gradient,
                            position: 'relative',
                            overflow: 'hidden',
                            cursor: 'pointer',
                            transition: 'all 0.3s ease',
                            borderRadius: '24px',
                            minHeight: '280px',
                            '&:hover': {
                                transform: 'translateY(-8px)',
                                boxShadow: '0 20px 40px rgba(0, 0, 0, 0.2)',
                            },
                            '&::before': {
                                content: '""',
                                position: 'absolute',
                                top: 0,
                                left: 0,
                                right: 0,
                                bottom: 0,
                                background: card.bgPattern,
                                pointerEvents: 'none'
                            }
                        }}
                    >
                        <CardContent
                            sx={{
                                position: 'relative',
                                zIndex: 1,
                                height: '100%',
                                display: 'flex',
                                flexDirection: 'column',
                                justifyContent: 'space-between',
                                p: 4
                            }}
                        >
                            <Box
                                sx={{
                                    width: 80,
                                    height: 80,
                                    borderRadius: '20px',
                                    backgroundColor: 'rgba(255, 255, 255, 0.2)',
                                    backdropFilter: 'blur(10px)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    color: '#fff',
                                    mb: 3
                                }}
                            >
                                {card.icon}
                            </Box>

                            <Box>
                                <Typography
                                    variant="h5"
                                    sx={{
                                        color: '#fff',
                                        fontWeight: 600,
                                        mb: 2,
                                        fontSize: '20px !important'
                                    }}
                                >
                                    {card.title}
                                </Typography>
                                <Typography
                                    variant="body1"
                                    sx={{
                                        color: 'rgba(255, 255, 255, 0.9)',
                                        lineHeight: 1.6
                                    }}
                                >
                                    {card.description}
                                </Typography>
                            </Box>
                        </CardContent>
                    </Card>
                ))}
            </Box>
        </Box>
    );
};

export default ReEngineeringCards;