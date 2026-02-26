/* Auto-generated test: test_2026-02-23_10-41 */
/* Module: cxpi */
/* Description: WRITE A C TEST CODE THAT INJECTS A TX CRC ERROR WHILE SENDING A RESPONSE AND VERIFIES THE SLAVE  DETECTS RX CRC ERROR. */
/* Generated: 2026-02-23T05:12:19.955Z */
/* LLM Model: claude-sonnet-4.5 */
/* LLM Enhanced: YES */

#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include "IfxCxpi_Cxpi.h"

/* === Static global variables === */
static IfxCxpi_t cxpiModule = {0};
static IfxCxpi_ErrorConfig_t errorConfig = {0};
static IfxCxpi_TestConfig_t testConfig = {0};
static IfxCxpi_ChannelConfig_t channelConfigMaster = {0};
static IfxCxpi_ChannelConfig_t channelConfigSlave = {0};
static IfxCxpi_Channel_t channelMaster = {0};
static IfxCxpi_Channel_t channelSlave = {0};
static IfxCxpi_ErrorFlags_t errorFlags = {0};
static IfxCxpi_IntrFlags_t intrFlags = {0};

static uint8_t txData[8] = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88};
static uint8_t rxData[8] = {0};
static uint8_t pId = 0x3C;
static IfxCxpi_DataLength_t dataLen = 8;
static uint16_t crc = 0;

uint8_t run_test(void);

uint8_t run_test(void)
{
    /* === [INIT] Module/channel initialization === */
    printf("[INIT] Starting initialization\n");

    /* Initialize error control configuration */
    printf("[INIT] Configuring error control module\n");
    IfxCxpi_initModuleConfigForErrorCtl(&errorConfig, &MODULE_CXPI0);
    errorConfig.errInjChannel = IfxCxpi_ChannelId_0;
    errorConfig.errorCtlEnable = TRUE;

    printf("[INIT] Initializing module for error control\n");
    IfxCxpi_initModuleForErrorCtl(&cxpiModule, &errorConfig);

    /* Initialize test/loopback configuration */
    printf("[INIT] Configuring test mode (loopback full disconnect)\n");
    IfxCxpi_initModuleConfigForTest(&testConfig, &MODULE_CXPI0);
    testConfig.testChannel = IfxCxpi_ChannelId_0;
    testConfig.testEnable = TRUE;
    testConfig.testMode = IfxCxpi_Loopback_fullDisconnect;

    printf("[INIT] Initializing module for test mode\n");
    IfxCxpi_Cxpi_initModuleForTest(&cxpiModule, &testConfig);

    /* === [CONFIG] Channel 0 - Master Configuration === */
    printf("[CONFIG] Configuring Channel 0 as Master\n");
    IfxCxpi_Cxpi_initChannelConfig(&channelConfigMaster, &cxpiModule);
    channelConfigMaster.autoEn = IfxCxpi_AutoEnState_enable;
    channelConfigMaster.baudrate = 9600;
    channelConfigMaster.channelId = IfxCxpi_ChannelId_0;
    channelConfigMaster.enableCh = IfxCxpi_ChState_enable;
    channelConfigMaster.mode = IfxCxpi_Mode_master;
    channelConfigMaster.opEncoding = IfxCxpi_OpEncoding_nrz;
    channelConfigMaster.configExt = NULL;

    printf("[CONFIG] Initializing Channel 0 (Master)\n");
    IfxCxpi_Cxpi_initChannel(&channelMaster, &channelConfigMaster);

    /* === [CONFIG] Channel 3 - Slave Configuration === */
    printf("[CONFIG] Configuring Channel 3 as Slave\n");
    IfxCxpi_Cxpi_initChannelConfig(&channelConfigSlave, &cxpiModule);
    channelConfigSlave.autoEn = IfxCxpi_AutoEnState_enable;
    channelConfigSlave.baudrate = 9600;
    channelConfigSlave.channelId = IfxCxpi_ChannelId_3;
    channelConfigSlave.enableCh = IfxCxpi_ChState_enable;
    channelConfigSlave.mode = IfxCxpi_Mode_slave;
    channelConfigSlave.opEncoding = IfxCxpi_OpEncoding_nrz;
    channelConfigSlave.configExt = NULL;

    printf("[CONFIG] Initializing Channel 3 (Slave)\n");
    IfxCxpi_Cxpi_initChannel(&channelSlave, &channelConfigSlave);

    /* === [SEQUENCE] Master sends header and response with injected CRC error === */
    printf("[SEQUENCE] Master: Sending header (PID: 0x%02X)\n", pId);
    IfxCxpi_Cxpi_sendHeader(&channelMaster, pId);

    printf("[BUSY-WAIT] Waiting for header transmission completion\n");
    while(IfxCxpi_getChannelStatus(&channelMaster, IfxCxpi_ChActivity_txHeaderDone) == IfxCxpi_ChStatus_busy);

    printf("[SEQUENCE] Injecting TX CRC error on Channel 0\n");
    IfxCxpi_injectTxError(&channelMaster, IfxCxpi_ErrInjTypes_txCrcError);

    printf("[SEQUENCE] Master: Transmitting response with CRC error\n");
    IfxCxpi_Cxpi_transmitResponse(&channelMaster, pId, txData, dataLen, crc);

    printf("[BUSY-WAIT] Waiting for response transmission completion\n");
    while(IfxCxpi_getChannelStatus(&channelMaster, IfxCxpi_ChActivity_txResponseDone) == IfxCxpi_ChStatus_busy);

    /* === [SEQUENCE] Slave enables reception and receives response === */
    printf("[SEQUENCE] Slave: Enabling reception for header\n");
    IfxCxpi_Cxpi_enableReception(&channelSlave, IfxCxpi_RxRequest_receiveHeader);

    printf("[SEQUENCE] Slave: Receiving header\n");
    IfxCxpi_Cxpi_receiveHeader(&channelSlave, &pId);

    printf("[BUSY-WAIT] Waiting for header reception completion\n");
    while(IfxCxpi_getChannelStatus(&channelSlave, IfxCxpi_ChActivity_rxHeaderDone) == IfxCxpi_ChStatus_busy);

    printf("[SEQUENCE] Slave: Enabling reception for response\n");
    IfxCxpi_Cxpi_enableReception(&channelSlave, IfxCxpi_RxRequest_receiveResponse);

    printf("[SEQUENCE] Slave: Receiving response\n");
    IfxCxpi_Cxpi_receiveResponse(&channelSlave, rxData, &dataLen, &crc);

    printf("[BUSY-WAIT] Waiting for response reception completion\n");
    while(IfxCxpi_getChannelStatus(&channelSlave, IfxCxpi_ChActivity_rxResponseDone) == IfxCxpi_ChStatus_busy);

    /* === [ERROR] Monitor for RX CRC error on slave === */
    printf("[ERROR] Monitoring slave for RX CRC error detection\n");
    while(errorFlags.rxCrcError == 0)
    {
        IfxCxpi_getErrorFlags(&channelSlave, &errorFlags);
    }
    printf("[ERROR] RX CRC error detected on slave\n");

    /* === [VALIDATION] Verify error flags === */
    printf("[VALIDATION] Error flags on slave:\n");
    printf("[VALIDATION]   rxCrcError: %u\n", errorFlags.rxCrcError);
    printf("[VALIDATION]   rxDataLengthError: %u\n", errorFlags.rxDataLengthError);
    printf("[VALIDATION]   rxFrameError: %u\n", errorFlags.rxFrameError);
    printf("[VALIDATION]   rxHeaderParityError: %u\n", errorFlags.rxHeaderParityError);
    printf("[VALIDATION]   rxOverflowError: %u\n", errorFlags.rxOverflowError);
    printf("[VALIDATION]   rxUnderflowError: %u\n", errorFlags.rxUnderflowError);

    /* === [FINALIZE] Cleanup === */
    printf("[FINALIZE] Clearing all interrupts on master channel\n");
    IfxCxpi_Cxpi_clearAllInterrupts(&channelMaster);

    printf("[FINALIZE] Clearing all interrupts on slave channel\n");
    IfxCxpi_Cxpi_clearAllInterrupts(&channelSlave);

    printf("[FINALIZE] Cleanup complete, returning\n");
    return 0;
}