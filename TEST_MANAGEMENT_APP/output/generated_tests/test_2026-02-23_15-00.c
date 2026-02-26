/* Auto-generated test: test_2026-02-23_15-00 */
/* Module: cxpi */
/* Description: WRITE A C TEST CODE THAT INJECTS A TX CRC ERROR WHILE SENDING A RESPONSE AND VERIFIES THE SLAVE DETECTS RX CRC ERROR. */
/* Generated: 2026-02-23T09:31:07.991Z */
/* LLM Model: claude-sonnet-4.5 */
/* LLM Enhanced: YES */

#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include "IfxCxpi_Cxpi.h"

#ifndef TRUE
#define TRUE 1
#endif

#ifndef FALSE
#define FALSE 0
#endif

#ifndef NULL
#define NULL ((void*)0)
#endif

/* === Static global variables === */
static IfxCxpi_t ifxCxpi = {0};
static IfxCxpi_Config_t config = {0};
static IfxCxpi_TestConfig_t testConfig = {0};
static IfxCxpi_ErrorConfig_t errorConfig = {0};
static IfxCxpi_ChannelConfig_t channelConfig_master = {0};
static IfxCxpi_ChannelConfig_t channelConfig_slave = {0};
static IfxCxpi_Channel_t channel_master = {0};
static IfxCxpi_Channel_t channel_slave = {0};
static IfxCxpi_ErrorFlags_t errorFlags = {0};
static IfxCxpi_IntrFlags_t intrFlags = {0};

static uint8_t txData[8] = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88};
static uint8_t rxData[8] = {0};
static uint8_t pId = 0x2A;
static IfxCxpi_DataLength_t dataLen = 8;
static uint16_t crc = 0;

uint8_t run_test(void);

uint8_t run_test(void)
{
    /* === [INIT] Initialization === */
    printf("[INIT] Starting initialization\n");

    printf("[INIT] Calling IfxCxpi_initModuleConfigForErrorCtl\n");
    IfxCxpi_initModuleConfigForErrorCtl(&errorConfig, &MODULE_CXPI0);
    errorConfig.errInjChannel = IfxCxpi_ChannelId_0;
    errorConfig.errorCtlEnable = TRUE;

    printf("[INIT] Calling IfxCxpi_initModuleForErrorCtl\n");
    IfxCxpi_initModuleForErrorCtl(&ifxCxpi, &errorConfig);

    printf("[INIT] Calling IfxCxpi_initModuleConfigForTest\n");
    IfxCxpi_initModuleConfigForTest(&testConfig, &MODULE_CXPI0);
    testConfig.testChannel = IfxCxpi_ChannelId_0;
    testConfig.testEnable = TRUE;
    testConfig.testMode = IfxCxpi_Loopback_fullDisconnect;

    printf("[INIT] Calling IfxCxpi_Cxpi_initModuleForTest\n");
    IfxCxpi_Cxpi_initModuleForTest(&ifxCxpi, &testConfig);

    /* === [CONFIG] Configuration === */
    printf("[CONFIG] Configuring master channel (channel 0)\n");

    printf("[CONFIG] Calling IfxCxpi_Cxpi_initChannelConfig for master\n");
    IfxCxpi_Cxpi_initChannelConfig(&channelConfig_master, &ifxCxpi);
    channelConfig_master.autoEn = IfxCxpi_AutoEnState_enable;
    channelConfig_master.baudrate = 9600;
    channelConfig_master.channelId = IfxCxpi_ChannelId_0;
    channelConfig_master.enableCh = IfxCxpi_ChState_enable;
    channelConfig_master.mode = IfxCxpi_Mode_master;
    channelConfig_master.opEncoding = IfxCxpi_OpEncoding_nrz;
    channelConfig_master.configExt = NULL;

    printf("[CONFIG] Calling IfxCxpi_Cxpi_initChannel for master\n");
    IfxCxpi_Cxpi_initChannel(&channel_master, &channelConfig_master);

    printf("[CONFIG] Configuring slave channel (channel 3)\n");

    printf("[CONFIG] Calling IfxCxpi_Cxpi_initChannelConfig for slave\n");
    IfxCxpi_Cxpi_initChannelConfig(&channelConfig_slave, &ifxCxpi);
    channelConfig_slave.autoEn = IfxCxpi_AutoEnState_enable;
    channelConfig_slave.baudrate = 9600;
    channelConfig_slave.channelId = IfxCxpi_ChannelId_3;
    channelConfig_slave.enableCh = IfxCxpi_ChState_enable;
    channelConfig_slave.mode = IfxCxpi_Mode_slave;
    channelConfig_slave.opEncoding = IfxCxpi_OpEncoding_nrz;
    channelConfig_slave.configExt = NULL;

    printf("[CONFIG] Calling IfxCxpi_Cxpi_initChannel for slave\n");
    IfxCxpi_Cxpi_initChannel(&channel_slave, &channelConfig_slave);

    /* === [SEQUENCE] Communication / operation sequence === */
    printf("[SEQUENCE] Starting main test sequence\n");

    printf("[SEQUENCE] Calling IfxCxpi_Cxpi_enableReception on slave\n");
    IfxCxpi_Cxpi_enableReception(&channel_slave, IfxCxpi_RxRequest_receiveHeader);

    printf("[SEQUENCE] Calling IfxCxpi_Cxpi_sendHeader on master\n");
    IfxCxpi_Cxpi_sendHeader(&channel_master, pId);

    printf("[BUSY-WAIT] Waiting for TX header completion on master\n");
    while(IfxCxpi_ChStatus_busy == IfxCxpi_getChannelStatus(&channel_master, IfxCxpi_ChActivity_txHeaderDone));

    printf("[SEQUENCE] Calling IfxCxpi_Cxpi_receiveHeader on slave\n");
    IfxCxpi_Cxpi_receiveHeader(&channel_slave, &pId);

    printf("[BUSY-WAIT] Waiting for RX header completion on slave\n");
    while(IfxCxpi_ChStatus_busy == IfxCxpi_getChannelStatus(&channel_slave, IfxCxpi_ChActivity_rxHeaderDone));

    printf("[SEQUENCE] Calling IfxCxpi_Cxpi_enableReception on slave for response\n");
    IfxCxpi_Cxpi_enableReception(&channel_slave, IfxCxpi_RxRequest_receiveResponse);

    printf("[SEQUENCE] Calling IfxCxpi_injectTxError on master\n");
    IfxCxpi_injectTxError(&channel_master, IfxCxpi_ErrInjTypes_txCrcError);

    printf("[SEQUENCE] Calling IfxCxpi_Cxpi_transmitResponse on master\n");
    IfxCxpi_Cxpi_transmitResponse(&channel_master, pId, txData, &dataLen, &crc);

    printf("[BUSY-WAIT] Waiting for TX response completion on master\n");
    while(IfxCxpi_ChStatus_busy == IfxCxpi_getChannelStatus(&channel_master, IfxCxpi_ChActivity_txResponseDone));

    printf("[SEQUENCE] Calling IfxCxpi_Cxpi_receiveResponse on slave\n");
    IfxCxpi_Cxpi_receiveResponse(&channel_slave, rxData, &dataLen, &crc);

    printf("[BUSY-WAIT] Waiting for RX response completion on slave\n");
    while(IfxCxpi_ChStatus_busy == IfxCxpi_getChannelStatus(&channel_slave, IfxCxpi_ChActivity_rxResponseDone));

    /* === [ERROR MONITORING] Poll for error detection === */
    printf("[ERROR MONITORING] Polling for rxCrcError on slave\n");
    while(errorFlags.rxCrcError == 0)
    {
        IfxCxpi_getErrorFlags(&channel_slave, &errorFlags);
    }
    printf("[ERROR MONITORING] Error detected: rxCrcError = %d\n", errorFlags.rxCrcError);

    /* === [VALIDATION] Data Verification === */
    printf("[VALIDATION] rxCrcError flag: %d\n", errorFlags.rxCrcError);
    printf("[VALIDATION] rxData[0]: 0x%02X\n", rxData[0]);
    printf("[VALIDATION] rxData[1]: 0x%02X\n", rxData[1]);
    printf("[VALIDATION] rxData[2]: 0x%02X\n", rxData[2]);
    printf("[VALIDATION] rxData[3]: 0x%02X\n", rxData[3]);
    printf("[VALIDATION] rxData[4]: 0x%02X\n", rxData[4]);
    printf("[VALIDATION] rxData[5]: 0x%02X\n", rxData[5]);
    printf("[VALIDATION] rxData[6]: 0x%02X\n", rxData[6]);
    printf("[VALIDATION] rxData[7]: 0x%02X\n", rxData[7]);

    /* === [FINALIZE] Cleanup === */
    printf("[FINALIZE] Calling IfxCxpi_Cxpi_clearAllInterrupts on master\n");
    IfxCxpi_Cxpi_clearAllInterrupts(&channel_master);

    printf("[FINALIZE] Calling IfxCxpi_Cxpi_clearAllInterrupts on slave\n");
    IfxCxpi_Cxpi_clearAllInterrupts(&channel_slave);

    printf("[FINALIZE] Cleanup complete, returning\n");
    return 0;
}