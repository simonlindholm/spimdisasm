#!/usr/bin/env python3

# SPDX-FileCopyrightText: © 2022 Decompollaborate
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Callable

from ... import common


class SymbolBase(common.ElementBase):
    def __init__(self, context: common.Context, vromStart: int, vromEnd: int, inFileOffset: int, vram: int, words: list[int], sectionType: common.FileSectionType, segmentVromStart: int, overlayCategory: str|None):
        super().__init__(context, vromStart, vromEnd, inFileOffset, vram, "", words, sectionType, segmentVromStart, overlayCategory)

        self.endOfLineComment: list[str] = []

        self.contextSym = self.addSymbol(self.vram, sectionType=self.sectionType, isAutogenerated=True)
        self.contextSym.vromAddress = self.vromStart
        self.contextSym.isDefined = True
        self.contextSym.sectionType = self.sectionType


    def getName(self) -> str:
        return self.contextSym.getName()

    def setNameIfUnset(self, name: str) -> None:
        self.contextSym.setNameIfUnset(name)

    def setNameGetCallback(self, callback: Callable[[common.ContextSymbol], str]) -> None:
        self.contextSym.setNameGetCallback(callback)

    def setNameGetCallbackIfUnset(self, callback: Callable[[common.ContextSymbol], str]) -> None:
        self.contextSym.setNameGetCallbackIfUnset(callback)


    def generateAsmLineComment(self, localOffset: int, wordValue: int|None = None) -> str:
        if not common.GlobalConfig.ASM_COMMENT:
            return ""

        offsetHex = "{0:0{1}X}".format(localOffset + self.inFileOffset + self.commentOffset, common.GlobalConfig.ASM_COMMENT_OFFSET_WIDTH)

        currentVram = self.getVramOffset(localOffset)
        vramHex = f"{currentVram:08X}"

        wordValueHex = ""
        if wordValue is not None:
            wordValueHex = f"{common.Utils.wordToCurrenEndian(wordValue):08X} "

        return f"/* {offsetHex} {vramHex} {wordValueHex}*/"


    def getExtraLabelFromSymbol(self, contextSym: common.ContextSymbol|None) -> str:
        label = ""
        if contextSym is not None:
            label = common.GlobalConfig.LINE_ENDS
            symLabel = contextSym.getSymbolLabel()
            if symLabel:
                label += symLabel + common.GlobalConfig.LINE_ENDS
                if common.GlobalConfig.ASM_DATA_SYM_AS_LABEL:
                    label += f"{contextSym.getName()}:" + common.GlobalConfig.LINE_ENDS
        return label


    def isByte(self, index: int) -> bool:
        return self.contextSym.isByte() and not self.isString()

    def isShort(self, index: int) -> bool:
        return self.contextSym.isShort()

    def isString(self) -> bool:
        return False

    def isFloat(self, index: int) -> bool:
        if self.contextSym.isFloat():
            word = self.words[index]
            # Filter out NaN and infinity
            if (word & 0x7F800000) != 0x7F800000:
                return True
        return False

    def isDouble(self, index: int) -> bool:
        if self.contextSym.isDouble():
            if index + 1 < self.sizew:
                word0 = self.words[index]
                word1 = self.words[index+1]
                # Filter out NaN and infinity
                if (((word0 << 32) | word1) & 0x7FF0000000000000) != 0x7FF0000000000000:
                    # Prevent accidentally losing symbols
                    currentVram = self.getVramOffset(index*4)
                    if self.getSymbol(currentVram+4, tryPlusOffset=False) is None:
                        return True
        return False

    def isJumpTable(self) -> bool:
        return False


    def isRdata(self) -> bool:
        "Checks if the current symbol is .rdata"
        return False


    def renameBasedOnType(self):
        pass


    def analyze(self):
        self.renameBasedOnType()

        byteStep = 4
        if self.contextSym.isByte():
            byteStep = 1
        elif self.contextSym.isShort():
            byteStep = 2

        if self.sectionType != common.FileSectionType.Bss:
            for i in range(0, self.sizew):
                localOffset = 4*i
                for j in range(0, 4, byteStep):
                    if i == 0 and j == 0:
                        continue
                    currentVram = self.getVramOffset(localOffset+j)
                    contextSym = self.getSymbol(currentVram, tryPlusOffset=False)
                    if contextSym is not None:
                        contextSym.vromAddress = self.getVromOffset(localOffset+j)
                        contextSym.isDefined = True
                        contextSym.sectionType = self.sectionType
                        if contextSym.hasNoType():
                            contextSym.type = contextSym.type


    def getJByteAsByte(self, i: int, j: int) -> str:
        localOffset = 4*i
        w = self.words[i]

        dotType = ".byte"

        shiftValue = j * 8
        if common.GlobalConfig.ENDIAN == common.InputEndian.BIG:
            shiftValue = 24 - shiftValue
        subVal = (w & (0xFF << shiftValue)) >> shiftValue
        value = f"0x{subVal:02X}"

        comment = self.generateAsmLineComment(localOffset+j)
        return f"{comment} {dotType} {value}"

    def getJByteAsShort(self, i: int, j: int) -> str:
        localOffset = 4*i
        w = self.words[i]

        dotType = ".short"

        shiftValue = j * 8
        if common.GlobalConfig.ENDIAN == common.InputEndian.BIG:
            shiftValue = 16 - shiftValue
        subVal = (w & (0xFFFF << shiftValue)) >> shiftValue
        value = f"0x{subVal:04X}"

        comment = self.generateAsmLineComment(localOffset+j)
        return f"{comment} {dotType} {value}"

    def getNthWordAsBytesAndShorts(self, i : int, sym1: common.ContextSymbol|None, sym2: common.ContextSymbol|None, sym3: common.ContextSymbol|None) -> tuple[str, int]:
        output = ""

        if sym1 is not None or self.isByte(i) or (not self.isShort(i) and sym3 is not None):
            output += self.getJByteAsByte(i, 0)
            output += common.GlobalConfig.LINE_ENDS

            output += self.getExtraLabelFromSymbol(sym1)
            output += self.getJByteAsByte(i, 1)
            output += common.GlobalConfig.LINE_ENDS
        else:
            output += self.getJByteAsShort(i, 0)
            output += common.GlobalConfig.LINE_ENDS

        output += self.getExtraLabelFromSymbol(sym2)
        if sym3 is not None or (sym2 is not None and sym2.isByte()) or (self.isByte(i) and (sym2 is None or not sym2.isShort())):
            output += self.getJByteAsByte(i, 2)
            output += common.GlobalConfig.LINE_ENDS

            output += self.getExtraLabelFromSymbol(sym3)
            output += self.getJByteAsByte(i, 3)
            output += common.GlobalConfig.LINE_ENDS
        else:
            output += self.getJByteAsShort(i, 2)
            output += common.GlobalConfig.LINE_ENDS

        return output, 0

    def getNthWordAsWords(self, i: int, canReferenceSymbolsWithAddends: bool=False, canReferenceConstants: bool=False) -> tuple[str, int]:
        output = ""
        localOffset = 4*i
        vram = self.getVramOffset(localOffset)
        w = self.words[i]

        dotType = ".word"

        label = ""
        if i != 0:
            label = self.getExtraLabelFromSymbol(self.getSymbol(vram, tryPlusOffset=False))

        value = f"0x{w:08X}"

        # .elf relocated symbol
        relocInfo = self.context.getRelocInfo(self.vram + localOffset, self.sectionType)
        if relocInfo is not None:
            if relocInfo.referencedSectionVram is not None:
                relocVram = relocInfo.referencedSectionVram + w
                contextSym = self.getSymbol(relocVram, checkUpperLimit=False)
                if contextSym is not None:
                    value = contextSym.getSymbolPlusOffset(relocVram)
            else:
                value = relocInfo.getNamePlusOffset(w)
        else:
            # This word could be a reference to a symbol
            symbolRef = self.getSymbol(w, tryPlusOffset=canReferenceSymbolsWithAddends)
            if symbolRef is not None:
                value = symbolRef.getSymbolPlusOffset(w)
            elif canReferenceConstants:
                constant = self.getConstant(w)
                if constant is not None:
                    value = constant.getName()

        comment = self.generateAsmLineComment(localOffset)
        output += f"{label}{comment} {dotType} {value}"
        if i < len(self.endOfLineComment):
            output += self.endOfLineComment[i]
        output += common.GlobalConfig.LINE_ENDS

        return output, 0

    def getNthWordAsFloat(self, i: int) -> tuple[str, int]:
        output = ""
        localOffset = 4*i
        vram = self.getVramOffset(localOffset)
        w = self.words[i]

        label = ""
        if i != 0:
            label = self.getExtraLabelFromSymbol(self.getSymbol(vram, tryPlusOffset=False))

        dotType = ".float"
        floatValue = common.Utils.wordToFloat(w)
        value = f"{floatValue:.10g}"

        comment = self.generateAsmLineComment(localOffset, w)
        output += f"{label}{comment} {dotType} {value}"
        if i < len(self.endOfLineComment):
            output += self.endOfLineComment[i]
        output += common.GlobalConfig.LINE_ENDS

        return output, 0

    def getNthWordAsDouble(self, i: int) -> tuple[str, int]:
        output = ""
        localOffset = 4*i
        vram = self.getVramOffset(localOffset)
        w = self.words[i]

        label = ""
        if i != 0:
            label = self.getExtraLabelFromSymbol(self.getSymbol(vram, tryPlusOffset=False))

        dotType = ".double"
        otherHalf = self.words[i+1]
        doubleWord = (w << 32) | otherHalf
        doubleValue = common.Utils.qwordToDouble(doubleWord)
        value = f"{doubleValue:.18g}"

        comment = self.generateAsmLineComment(localOffset, doubleWord)
        output += f"{label}{comment} {dotType} {value}"
        if i < len(self.endOfLineComment):
            output += self.endOfLineComment[i]
        output += common.GlobalConfig.LINE_ENDS

        return output, 1

    def getNthWord(self, i: int, canReferenceSymbolsWithAddends: bool=False, canReferenceConstants: bool=False) -> tuple[str, int]:
        return self.getNthWordAsWords(i, canReferenceSymbolsWithAddends=canReferenceSymbolsWithAddends, canReferenceConstants=canReferenceConstants)


    def countExtraPadding(self) -> int:
        "Returns how many extra word paddings this symbol has"
        return 0

    def getPrevAlignDirective(self, i: int=0) -> str:
        return ""

    def getPostAlignDirective(self, i: int=0) -> str:
        return ""

    def disassembleAsData(self, useGlobalLabel: bool=True) -> str:
        output = ""
        if useGlobalLabel:
            output += self.getPrevAlignDirective(0)
            output += self.getLabelFromSymbol(self.contextSym)
            if common.GlobalConfig.ASM_DATA_SYM_AS_LABEL:
                output += f"{self.getName()}:" + common.GlobalConfig.LINE_ENDS
        else:
            output += f"{self.getName()}:" + common.GlobalConfig.LINE_ENDS

        canReferenceSymbolsWithAddends = self.canUseAddendsOnData()
        canReferenceConstants = self.canUseConstantsOnData()

        i = 0
        while i < self.sizew:
            vram = self.getVramOffset(i*4)

            sym1 = self.getSymbol(vram+1, tryPlusOffset=False, checkGlobalSegment=False)
            sym2 = self.getSymbol(vram+2, tryPlusOffset=False, checkGlobalSegment=False)
            sym3 = self.getSymbol(vram+3, tryPlusOffset=False, checkGlobalSegment=False)

            # Check for symbols in the middle of this word
            if sym1 is not None or sym2 is not None or sym3 is not None or self.isByte(i) or self.isShort(i):
                data, skip = self.getNthWordAsBytesAndShorts(i, sym1, sym2, sym3)
            elif self.isFloat(i):
                data, skip = self.getNthWordAsFloat(i)
            elif self.isDouble(i):
                data, skip = self.getNthWordAsDouble(i)
            else:
                data, skip = self.getNthWord(i, canReferenceSymbolsWithAddends, canReferenceConstants)

            if i != 0:
                output += self.getPrevAlignDirective(i)
            output += data
            output += self.getPostAlignDirective(i)

            i += skip
            i += 1
        return output

    def disassemble(self, migrate: bool=False, useGlobalLabel: bool=True) -> str:
        return self.disassembleAsData(useGlobalLabel=useGlobalLabel)
