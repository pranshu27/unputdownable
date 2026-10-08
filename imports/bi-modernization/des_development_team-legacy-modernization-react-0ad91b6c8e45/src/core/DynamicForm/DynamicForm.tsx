import React from "react";
import {
    TextField,
    MenuItem,
    InputLabel,
    Select,
    FormControl,
    FormHelperText,
    OutlinedInput,
    Checkbox,
    ListItemText,
    Box,
    Button,
    Typography,
} from "@mui/material";

const DynamicForm = ({
    config = [],
    formData = {},
    errors = {},
    onChange,
    onSubmit,
    onReset,
    showSubmitButton = false,
    showResetButton = false,
    submitText = "Submit",
    resetText = "Reset",
    inputSize = "small",
    layout = "vertical",
}) => {
    const getSizeProps = () => {
        switch (inputSize) {
            case "small":
                return { size: "small", sx: { fontSize: "0.8rem", height: 40 } };
            case "large":
                return { size: "medium", sx: { fontSize: "1.1rem", height: 56 } };
            default:
                return { size: "medium", sx: { fontSize: "1rem", height: 48 } };
        }
    };

    const sizeProps = getSizeProps();

    return (
        <Box
            display="flex"
            flexDirection={layout === "vertical" ? "column" : "row"}
            flexWrap={layout === "horizontal" ? "wrap" : "nowrap"}
            gap={2}
        >
            {config.map((field) => (
                <Box
                    key={field.name}
                    sx={{
                        width: layout === "vertical" ? "100%" : field.fieldWidth || "48%",
                        minWidth: 150,
                    }}
                >
                    <InputLabel shrink>
                        {field.label}
                        {field.required && <sup style={{ color: "red" }}>*</sup>}
                    </InputLabel>

                    <FormControl fullWidth error={!!errors[field.name]} required={field.required}>
                        {["text", "email", "number"].includes(field.type) && (
                            <TextField
                                type={field.type}
                                placeholder={field.placeholder}
                                value={formData[field.name] || ""}
                                onChange={(e) => onChange(field.name, e.target.value)}
                                {...sizeProps}
                                inputProps={{
                                    maxLength: field.maxLength,
                                    minLength: field.minLength,
                                    pattern: field.pattern,
                                    min: field.min,
                                    max: field.max,
                                }}
                            />
                        )}

                       import { MenuItem, Select, OutlinedInput } from '@mui/material';

{field.type === "select" && (
    <Select
        value={formData[field.name] || ""}
        onChange={(e) => onChange(field.name, e.target.value)}
        input={<OutlinedInput />}
        displayEmpty
        {...sizeProps}
        MenuProps={{
            PaperProps: {
                sx: {
                    '& .MuiMenuItem-root': {
                        color: '#64748B !important',
                    },
                },
            },
        }}
    >
        <MenuItem disabled value="">
            Select {field.label}
        </MenuItem>
        {field.options?.map((opt) => (
            <MenuItem
                key={opt}
                value={opt}
                sx={{
                    color: '#64748B !important', 
                }}
            >
                {opt}
            </MenuItem>
        ))}
    </Select>
)}


                        {field.type === "multiselect" && (
                            <Select
                                multiple
                                displayEmpty
                                value={formData[field.name] || []}
                                onChange={(e) => onChange(field.name, e.target.value)}
                                input={<OutlinedInput />}
                                renderValue={(selected) => {
                                    if (!selected.length) {
                                        return <span>{field.placeholder || `Select ${field.label}`}</span>;
                                    }
                                    return selected.join(", ");
                                }}
                                {...sizeProps}
                            >
                                <MenuItem disabled value="">
                                    <em>{field.placeholder || `Select ${field.label}`}</em>
                                </MenuItem>
                                {field.options?.map((opt) => {
                                    const selectedValues = formData[field.name] || [];
                                    const isSelected = selectedValues.includes(opt);

                                    return (
                                        <MenuItem key={opt} value={opt}>
                                            <Checkbox
                                                checked={isSelected}
                                                onChange={() => {
                                                    const newValue = isSelected
                                                        ? selectedValues.filter((v) => v !== opt)
                                                        : [...selectedValues, opt];
                                                    onChange(field.name, newValue);
                                                }}
                                            />
                                            <ListItemText
                                                primary={opt}
                                                onClick={() => {
                                                    const newValue = isSelected
                                                        ? selectedValues.filter((v) => v !== opt)
                                                        : [...selectedValues, opt];
                                                    onChange(field.name, newValue);
                                                }}
                                                sx={{ cursor: "pointer" }}
                                            />
                                        </MenuItem>
                                    );
                                })}
                            </Select>
                        )}

                        {field.type === "file" && (
                            <input
                                type="file"
                                accept={field.accept}
                                onChange={(e) => onChange(field.name, e.target.files[0])}
                                style={{
                                    fontSize: sizeProps.sx.fontSize,
                                    height: sizeProps.sx.height,
                                    padding: "8px",
                                }}
                            />
                        )}

                        {field.type === "default" && (
                            <Box
                                sx={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    py: 0.5,
                                }}
                            >
                                <Typography
                                    variant="body2"
                                    sx={{ color: "#444", fontWeight: 500 }}
                                >
                                    {field.label}
                                </Typography>
                                <Typography
                                    variant="body2"
                                    sx={{ color: "#000", textAlign: "right", maxWidth: "60%" }}
                                    noWrap
                                    title={formData[field.name]}
                                >
                                    {formData[field.name] || "-"}
                                </Typography>
                            </Box>
                        )}

                        {errors[field.name] && (
                            <FormHelperText>{errors[field.name]}</FormHelperText>
                        )}
                    </FormControl>
                </Box>
            ))}

            {(showSubmitButton || showResetButton) && (
                <Box
                    display="flex"
                    justifyContent="flex-end"
                    alignItems="center"
                    gap={2}
                    width="100%"
                    mt={2}
                >
                    {showResetButton && (
                        <Button variant="outlined" onClick={onReset}>
                            {resetText}
                        </Button>
                    )}
                    {showSubmitButton && (
                        <Button variant="contained" onClick={onSubmit}>
                            {submitText}
                        </Button>
                    )}
                </Box>
            )}
        </Box>
    );
};

export default DynamicForm;
