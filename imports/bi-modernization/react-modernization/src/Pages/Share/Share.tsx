import { useState } from "react";
import CustomPopup from "../../core/CustomPopup/CustomPopup.tsx";
import { Box, Typography, TextField, Checkbox, Avatar, Button, IconButton, InputAdornment } from '@mui/material';
import { useLocation, useNavigate } from 'react-router-dom';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SearchIcon from '@mui/icons-material/Search';
import fileIcon from '../../Assets/uploadImg.svg';
import { IMAGE_PATHS } from "../../Assets/Themes/CLIENT_Btheme.ts";
import Toaster from "../../core/Toaster/Toaster.tsx";
import CheckCircleIcon from '@mui/icons-material/CheckCircle';

const Share = () => {
    const dummyUsers = [
        { name: 'Shakeeb Faizan', email: 'smohammad@dataeconomy.ai' },
        { name: 'Vivek', email: 'vpedapenki@dataeconomy.ai' },
        { name: 'Prapurna', email: 'pjagarlamudi@dataeconomy.ai' },
        
    ];
    const [openPopup, setopenPopup] = useState(true);
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handlePopupClose = () => setopenPopup(false);
    const { state } = useLocation();
    const file = state?.file;

    const [search, setSearch] = useState('');
    const [selectedUsers, setSelectedUsers] = useState<string[]>([]);

    const toggleUser = (email: string) => {
        setSelectedUsers((prev) =>
            prev.includes(email) ? prev.filter((e) => e !== email) : [...prev, email]
        );
    };

     const [toast, setToast] = useState({
            open: false,
            title: '',
            message: '',
            severity: 'success',
            icon: null,
        });

    const handleSecondaryBtnClick = () => {
        navigate(-1);
    }

      const handleToasterClose = () => {
        setToast({ ...toast, open: false })
    }

    const handlePrimaryClick = () => {
        console.log(selectedUsers);
          setToast({
                    open: true,
                    title: 'Upload Successful',
                    message: 'File Shared successfully.',
                    severity: 'success',
                    icon: <CheckCircleIcon fontSize="inherit" />
                })
        navigate('/analyze');
    }


    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        return `${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · ${date.toDateString()}`;
    };

    const stringToColor = (str) => {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = str.charCodeAt(i) + ((hash << 5) - hash);
        }
        const color = `hsl(${hash % 360}, 60%, 60%)`;
        return color;
    };

    const filteredUsers = dummyUsers.filter(
        (u) =>
            u.name.toLowerCase().includes(search.toLowerCase()) ||
            u.email.toLowerCase().includes(search.toLowerCase())
    );

      const AnalyzedBy = ({ analysedBy }) => {
            const name = analysedBy.includes('user') ? 'You' : analysedBy.split('@')[0];
            const firstLetter = name.charAt(0).toUpperCase();
            const bgColor = stringToColor(name);
    
            return (
                <Box
                    display="flex"
                    alignItems="center"
                    border="1px solid #ccc"
                    borderRadius="20px"
                    px={1.5}
                    py={0.5}
                    width="fit-content"
                    gap={1}
                >
                    <Avatar sx={{ bgcolor: bgColor, width: 28, height: 28, fontSize: 14 }}>
                        {firstLetter}
                    </Avatar>
                    <Typography variant="body2">{name}</Typography>
                </Box>
            );
        };

    const messageContent = (
        <Box>
            <Box
                sx={{
                    border: '1px solid #eee',
                    p: 2,
                    borderRadius: '20px',
                    mb: 2,
                    backgroundColor: '#ffffff',
                }}
            >
                <Box
                    sx={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        textAlign: 'center',
                        gap: 1.2,
                    }}
                >
                    <img src={fileIcon} width={50} alt="File Icon" />

                    <Typography fontWeight={600} sx={{ color: '#296BC2' }}>
                        Share file:
                    </Typography>

                    <Typography
                        sx={{
                            color: '#296BC2',
                            fontWeight: 500,
                            wordBreak: 'break-word',
                            maxWidth: '100%',
                        }}
                    >
                        {file?.fileName}
                    </Typography>

                     <Box display="flex" alignItems="center" gap={1}>
                        <AnalyzedBy analysedBy={file.analysedBy} />
                        <Typography variant="caption" color="#64738B">
                            {formatDate(file.date)}
                        </Typography>
                    </Box>
                </Box>

            </Box>

            <TextField
                fullWidth
                placeholder="Search"
                value={search}
                variant="outlined"
                onChange={e => setSearch(e.target.value)}
                sx={{
                    '& .MuiOutlinedInput-root': {
                        borderRadius: '28px',
                        backgroundColor: '#fff',
                        height: '48px',
                        paddingRight: '16px',
                        marginBottom: '15px'
                    }
                }}
                InputProps={{
                    endAdornment: (
                        <InputAdornment position="end">
                            <SearchIcon />
                        </InputAdornment>
                    )
                }}
            />


            <Box sx={{ maxHeight: 'calc(100vh - 495px)', overflowY: 'auto', mb: 3 }}>
                {filteredUsers.map((user, i) => (
                    <Box
                        key={i}
                        display="flex"
                        alignItems="center"
                        justifyContent="space-between"
                        py={1}
                        sx={{ borderBottom: '1px solid #eee' }}
                    >
                        <Box display="flex" alignItems="center" gap={1}>
                            <Avatar sx={{ bgcolor: stringToColor(user.name) }}>{user.name.charAt(0)}</Avatar>
                            <Box>
                                <Typography>{user.name}</Typography>
                                <Typography fontSize={12} color="text.secondary">
                                    {user.email}
                                </Typography>
                            </Box>
                        </Box>
                        <Checkbox
                            checked={selectedUsers.includes(user.email)}
                            onChange={() => toggleUser(user.email)}
                        />
                    </Box>
                ))}
            </Box>
        </Box>
    )
    return (
        <>
            <CustomPopup
                sx={{ width: 780, backdropFilter: 'blur(160px)', boxShadow: ' 30px 30px 100px 0px rgba(0, 0, 0, 0.5)', borderRadius: '24px !important' }}
                showCloseIcon={false}
                open={openPopup}
                onClose={handlePopupClose}
                title="XCompanion"
                titleStylings={{
                    textAlign: 'center',
                    fontWeight: 500,
                    fontSize: '32px !important',
                    background: 'linear-gradient(90deg, #003087 0%, #C5162D 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    padding: '0px 24px',
                }}
                message={messageContent}
                showPrimaryButton={true}
                showSecondaryButton={true}
                disableBackdropClick={true}
                popupWidth="730px"
                popupbackgroundColor='#ffffff'
                popupBackgroundImage={IMAGE_PATHS.loginBg}
                onPrimaryClick={handlePrimaryClick}
                onSecondaryClick={handleSecondaryBtnClick}
                primaryBtnText="Share"
                secondaryBtnText="Back"
                secondaryBtnSx={{
                    background: '#ffffff',
                    borderRadius: '12px',
                    width: '178px',
                    '&:hover': {
                        backgroundColor: '#ffffff',
                    },
                }}
                primaryBtnSx={{
                    background: 'linear-gradient(to bottom, #b31429 0%, #b31429 50%, #a0042b 50%, #a0042b 100%)',
                    borderRadius: '12px',
                    width: '178px',
                    '&:hover': {
                        backgroundColor: 'linear-gradient(to bottom, #b31429 0%, #b31429 50%, #a0042b 50%, #a0042b 100%)',
                    },
                }}
            />

              <Toaster
                            open={toast.open}
                            onClose={handleToasterClose}
                            title={toast.title}
                            message={toast.message}
                            icon={toast.icon}
                            severity={toast.severity}
                            duration={4000}
                        />
        </>
    )
}

export default Share;