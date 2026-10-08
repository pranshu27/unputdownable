import React, { useState, useRef, useEffect } from 'react';
import CustomPopup from '../../core/CustomPopup/CustomPopup.tsx';
import {
    Box,
    Typography,
} from '@mui/material';
import Loader from '../../core/Loader/Loader.tsx';
import { useNavigate } from 'react-router-dom';
import './LegacyModernization.scss';
import { IMAGE_PATHS } from '../../../src/Assets/Themes/farmerstheme.ts';
import upload from '../../Assets/upload.svg';
import analyse from '../../Assets/uploadImg.svg';

const LegacyModernization = () => {
    const [openPopup, setopenPopup] = useState(true);
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handlePopupClose = () => setopenPopup(false);
    const handleSelectedOptionClick = (type: any) => {
        navigate(`/${type}`);
    }
    const messageContent = (
        <Box>
            <Typography variant="body1" sx={{ mb: 1, color: 'rgba(0, 48, 135, 1)', fontSize: '20px !important', fontWeight: '600' }}>
                SDLC Companion
            </Typography>
            <Typography variant="body1" sx={{ mb: 2, color: 'rgba(92,123,179,1)', fontSize: '14px !important', fontWeight: '00' }}>
                Sources refer to the datasets or connections used to build visualizations,
                which can be databases, files, or live APIs. Examples include Excel spreadsheets,
                SQL databases, and cloud services like Salesforce.
            </Typography>

            <div className="card-container">
                <div className="card" onClick={() => handleSelectedOptionClick('upload')}>
                    <div className="icon-wrapper">
                        <img src={upload} alt="Upload" className="icon" />
                    </div>
                    <Typography>Upload New Source File</Typography>
                </div>
                <div className="card" onClick={() => handleSelectedOptionClick('analyze')}>
                     <div className="icon-wrapper">
                         <img src={analyse} alt="Analyze" className="icon" />
                     </div>
                    <Typography>Analyze Existing Source</Typography>
                </div>
            </div>
        </Box>
    );

    return (
        <>
            <div className='legacy-container' >
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
                        background: 'linear-gradient(90deg, #ED1C24 0%, #FFCB05 35%, #A6CE39 66.5%, #44C8F5 100%)',
                        WebkitBackgroundClip: 'text',
                        WebkitTextFillColor: 'transparent',
                    }}
                    message={messageContent}
                    showPrimaryButton={false}
                    showSecondaryButton={false}
                    disableBackdropClick={true}
                    popupWidth="730px"
                    popupbackgroundColor='#E7EEF8E5'
                    popupBackgroundImage={IMAGE_PATHS.loginBg}

                />
            </div>
            <Loader show={loading} />
        </>
    );
};

export default LegacyModernization;
